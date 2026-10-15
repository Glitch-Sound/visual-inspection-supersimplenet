"""Source-group splitting and Optuna search."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
import optuna

from app.common.config import AppConfig, GroupConfig
from app.common.contracts import PreparationManifest


@dataclass(frozen=True)
class DatasetSplit:
    train_sources: tuple[str, ...]
    validation_sources: tuple[str, ...]
    train_images: tuple[Path, ...]
    validation_images: tuple[Path, ...]
    synthetic_images: tuple[Path, ...] = ()
    synthetic_error: str | None = None


def split_by_source(
    manifest: PreparationManifest,
    prepared_dir: Path,
    *,
    train_ratio: float = 0.8,
    seed: int = 42,
) -> DatasetSplit:
    usable = [source for source in manifest.sources if source.splits]
    source_names = sorted(source.source_image for source in usable)
    if len(source_names) < 2:
        raise ValueError(
            f"at least 2 source images are required; current count is {len(source_names)}"
        )
    np.random.default_rng(seed).shuffle(source_names)
    train_count = max(
        1, min(len(source_names) - 1, round(len(source_names) * train_ratio))
    )
    train_sources = tuple(sorted(source_names[:train_count]))
    validation_sources = tuple(sorted(source_names[train_count:]))
    if not train_sources or not validation_sources:
        raise ValueError(
            f"both train and validation sets are required; current count is {len(source_names)}"
        )
    by_source = {source.source_image: source for source in usable}
    train_images = tuple(
        prepared_dir / split.image
        for name in train_sources
        for split in by_source[name].splits
    )
    validation_images = tuple(
        prepared_dir / split.image
        for name in validation_sources
        for split in by_source[name].splits
    )
    return DatasetSplit(
        train_sources,
        validation_sources,
        train_images,
        validation_images,
    )


@dataclass(frozen=True)
class TrialParameters:
    learning_rate_multiplier: float
    batch_size: int
    epochs: int
    feature_layers: list[str]
    image_size: int


@dataclass(frozen=True)
class TrialOutcome:
    validation_scores: list[float]
    training_scores: list[float]
    checkpoint: Path
    synthetic_scores: list[float] | None = None


class TrialRunner(Protocol):
    def __call__(
        self,
        parameters: TrialParameters,
        split: DatasetSplit,
        trial: optuna.Trial,
    ) -> TrialOutcome: ...


def suggest_parameters(trial: optuna.Trial, group: GroupConfig) -> TrialParameters:
    search = group.optuna_settings.search
    feature_layers = json.loads(
        trial.suggest_categorical(
            "feature_layers",
            [json.dumps(value) for value in search.feature_layers.choices],
        )
    )
    return TrialParameters(
        learning_rate_multiplier=trial.suggest_float(
            "learning_rate_multiplier",
            search.learning_rate_multiplier.low,
            search.learning_rate_multiplier.high,
            log=search.learning_rate_multiplier.log,
        ),
        batch_size=trial.suggest_categorical("batch_size", search.batch_size.choices),
        epochs=trial.suggest_categorical("epochs", search.epochs.choices),
        feature_layers=feature_layers,
        image_size=trial.suggest_categorical(
            "image_size", search.preprocessing.image_size.choices
        ),
    )


def create_study(config: AppConfig, group: GroupConfig, storage: Path) -> optuna.Study:
    settings = group.optuna_settings
    storage.parent.mkdir(parents=True, exist_ok=True)
    sampler = optuna.samplers.TPESampler(seed=settings.sampler.seed)
    pruner = optuna.pruners.MedianPruner(
        n_startup_trials=settings.pruner.startup_trials,
        n_warmup_steps=settings.pruner.warmup_epochs,
        interval_steps=settings.pruner.interval_epochs,
    )
    study = optuna.create_study(
        study_name=f"visual-inspection-{config.model}-group-{group.id}",
        storage=f"sqlite:///{storage}",
        load_if_exists=settings.execution.resume,
        direction=(
            "maximize" if settings.objective == "synthetic_auroc" else "minimize"
        ),
        sampler=sampler,
        pruner=pruner,
    )
    contract = {
        "objective": settings.objective,
        "synthetic_validation": settings.synthetic_validation.model_dump(),
        "split_seed": settings.normal_only.seed,
        "sampler_seed": settings.sampler.seed,
        "execution_seed": settings.execution.seed,
    }
    previous = study.user_attrs.get("evaluation_contract")
    if study.trials and previous is None:
        legacy = (
            settings.objective == "normal_percentile"
            and settings.synthetic_validation.model_fields_set == set()
        )
        if not legacy:
            raise ValueError(
                "evaluation contract differs from existing study; use train --restart"
            )
    elif previous is not None and not isinstance(previous, dict):
        raise ValueError(
            "invalid evaluation contract in existing study; use train --restart"
        )
    elif previous is not None and previous != contract:
        differing = [key for key in contract if previous.get(key) != contract[key]]
        raise ValueError(
            f"evaluation contract differs ({', '.join(differing)}); use train --restart"
        )
    study.set_user_attr("evaluation_contract", contract)
    return study


def synthetic_auroc(normal: list[float], synthetic: list[float]) -> float:
    """Pairwise AUROC with half credit for equal scores."""
    n = np.asarray(normal, dtype=float)
    s = np.asarray(synthetic, dtype=float)
    if not len(n) or not len(s) or not np.isfinite(n).all() or not np.isfinite(s).all():
        raise ValueError(
            "synthetic AUROC requires nonempty finite normal and synthetic scores"
        )
    comparisons = s[:, None] - n[None, :]
    return float(np.mean((comparisons > 0) + 0.5 * (comparisons == 0)))


def score_summary(scores: list[float]) -> dict[str, float | int]:
    values = np.asarray(scores, dtype=float)
    if not len(values) or not np.isfinite(values).all():
        raise ValueError("synthetic score summary requires nonempty finite scores")
    return {
        "count": int(len(values)),
        "min": float(np.min(values)),
        "median": float(np.median(values)),
        "p99": float(np.percentile(values, 99)),
        "max": float(np.max(values)),
    }


def run_search(
    group: GroupConfig,
    split: DatasetSplit,
    study: optuna.Study,
    runner: TrialRunner,
    *,
    on_trial_start: Callable[[int, TrialParameters], None] | None = None,
    on_trial_finish: Callable[[optuna.trial.FrozenTrial], None] | None = None,
) -> tuple[optuna.Study, dict[int, TrialOutcome]]:
    settings = group.optuna_settings
    outcomes: dict[int, TrialOutcome] = {}

    def objective(trial: optuna.Trial) -> float:
        try:
            return evaluate_trial(trial)
        except Exception as error:
            trial.set_user_attr("failure_reason", f"{type(error).__name__}: {error}")
            raise

    def evaluate_trial(trial: optuna.Trial) -> float:
        if split.synthetic_error is not None:
            raise ValueError(
                f"synthetic validation generation failed: {split.synthetic_error}"
            )
        parameters = suggest_parameters(trial, group)
        if on_trial_start is not None:
            on_trial_start(trial.number, parameters)
        outcome = runner(parameters, split, trial)
        normal = np.asarray(outcome.validation_scores, dtype=float)
        if not len(normal) or not np.isfinite(normal).all():
            raise ValueError("validation produced no finite pred_score values")
        normal_p99 = float(np.percentile(normal, 99))
        auc: float | None = None
        summary: dict[str, float | int] | None = None
        if outcome.synthetic_scores is not None:
            auc = synthetic_auroc(outcome.validation_scores, outcome.synthetic_scores)
            summary = score_summary(outcome.synthetic_scores)
        if settings.objective == "synthetic_auroc":
            if auc is None:
                raise ValueError("synthetic AUROC requires synthetic validation scores")
            objective_value = auc
        else:
            objective_value = float(
                np.percentile(normal, settings.normal_only.percentile)
            )
        trial.set_user_attr("checkpoint", str(outcome.checkpoint))
        trial.set_user_attr("training_scores", outcome.training_scores)
        trial.set_user_attr("normal_p99", normal_p99)
        trial.set_user_attr("synthetic_auroc", auc)
        trial.set_user_attr("synthetic_scores_summary", summary)
        trial.report(objective_value, parameters.epochs)
        if settings.objective == "normal_percentile" and trial.should_prune():
            raise optuna.TrialPruned()
        outcomes[trial.number] = outcome
        return objective_value

    remaining = max(0, settings.execution.trials - len(study.trials))
    if split.synthetic_error is not None:
        remaining = min(remaining, 1)
    callbacks = (
        [lambda _study, trial: on_trial_finish(trial)]
        if on_trial_finish is not None
        else None
    )
    study.optimize(
        objective, n_trials=remaining, catch=(Exception,), callbacks=callbacks
    )
    if not study.best_trials:
        raise RuntimeError("all Optuna trials failed or were pruned")
    return study, outcomes
