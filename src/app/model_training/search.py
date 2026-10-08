"""Source-group splitting and Optuna search."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
import optuna

from app.common.config import AppConfig
from app.common.contracts import PreparationManifest


@dataclass(frozen=True)
class DatasetSplit:
    train_sources: tuple[str, ...]
    validation_sources: tuple[str, ...]
    train_images: tuple[Path, ...]
    validation_images: tuple[Path, ...]


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


class TrialRunner(Protocol):
    def __call__(
        self,
        parameters: TrialParameters,
        split: DatasetSplit,
        trial: optuna.Trial,
    ) -> TrialOutcome: ...


def suggest_parameters(trial: optuna.Trial, config: AppConfig) -> TrialParameters:
    search = config.part.optuna_settings.search
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


def create_study(config: AppConfig, storage: Path) -> optuna.Study:
    settings = config.part.optuna_settings
    storage.parent.mkdir(parents=True, exist_ok=True)
    sampler = optuna.samplers.TPESampler(seed=settings.sampler.seed)
    pruner = optuna.pruners.MedianPruner(
        n_startup_trials=settings.pruner.startup_trials,
        n_warmup_steps=settings.pruner.warmup_epochs,
        interval_steps=settings.pruner.interval_epochs,
    )
    return optuna.create_study(
        study_name=f"visual-inspection-{config.model}",
        storage=f"sqlite:///{storage}",
        load_if_exists=settings.execution.resume,
        direction="minimize",
        sampler=sampler,
        pruner=pruner,
    )


def run_search(
    config: AppConfig,
    split: DatasetSplit,
    study: optuna.Study,
    runner: TrialRunner,
    *,
    on_trial_start: Callable[[int, TrialParameters], None] | None = None,
    on_trial_finish: Callable[[optuna.trial.FrozenTrial], None] | None = None,
) -> tuple[optuna.Study, dict[int, TrialOutcome]]:
    settings = config.part.optuna_settings
    outcomes: dict[int, TrialOutcome] = {}

    def objective(trial: optuna.Trial) -> float:
        parameters = suggest_parameters(trial, config)
        if on_trial_start is not None:
            on_trial_start(trial.number, parameters)
        outcome = runner(parameters, split, trial)
        if not outcome.validation_scores:
            raise ValueError("validation produced no pred_score values")
        objective_value = float(
            np.percentile(outcome.validation_scores, settings.normal_only.percentile)
        )
        trial.set_user_attr("checkpoint", str(outcome.checkpoint))
        trial.set_user_attr("training_scores", outcome.training_scores)
        trial.report(objective_value, parameters.epochs)
        if trial.should_prune():
            raise optuna.TrialPruned()
        outcomes[trial.number] = outcome
        return objective_value

    remaining = max(0, settings.execution.trials - len(study.trials))
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
