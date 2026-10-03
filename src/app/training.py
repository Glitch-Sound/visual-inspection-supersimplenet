"""Source-group splitting, Optuna search, and model artifact persistence."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
import optuna

from app.config import AppConfig, write_threshold
from app.contracts import BestTrialResult, PreparationManifest, ScoreContract
from app.modeling import (
    AnomalibTrainingAugmentation,
    create_supersimplenet,
    extract_predictions,
)
from app.paths import ProjectPaths
from app.runtime import DeviceSelection, package_versions


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


def format_training_summary(result: BestTrialResult) -> str:
    return f"暫定探索指標={result.objective} threshold={result.threshold}"


class TrialRunner(Protocol):
    def __call__(
        self,
        parameters: TrialParameters,
        split: DatasetSplit,
        trial: optuna.Trial,
    ) -> TrialOutcome: ...


def create_pruning_callback(
    trial: optuna.Trial, *, percentile: float, interval_epochs: int
):
    """Report validation raw-score percentiles to Optuna at fixed epochs."""

    from lightning.pytorch.callbacks import Callback

    class RawScorePruningCallback(Callback):
        def __init__(self) -> None:
            self.scores: list[float] = []

        def on_validation_epoch_start(self, trainer, pl_module) -> None:
            del trainer, pl_module
            self.scores.clear()

        def on_validation_batch_end(
            self,
            trainer,
            pl_module,
            outputs,
            batch,
            batch_idx,
            dataloader_idx=0,
        ) -> None:
            del pl_module, batch, batch_idx, dataloader_idx
            if trainer.sanity_checking or outputs is None:
                return
            self.scores.extend(extract_predictions([outputs]))

        def on_validation_epoch_end(self, trainer, pl_module) -> None:
            del pl_module
            step = trainer.current_epoch + 1
            if (
                trainer.sanity_checking
                or not self.scores
                or step % interval_epochs != 0
            ):
                return
            value = float(np.percentile(self.scores, percentile))
            trial.report(value, step)
            if trial.should_prune():
                raise optuna.TrialPruned(f"pruned at epoch {step}")

    return RawScorePruningCallback()


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
) -> tuple[optuna.Study, dict[int, TrialOutcome]]:
    settings = config.part.optuna_settings
    outcomes: dict[int, TrialOutcome] = {}

    def objective(trial: optuna.Trial) -> float:
        parameters = suggest_parameters(trial, config)
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
    study.optimize(objective, n_trials=remaining, catch=(Exception,))
    if not study.best_trials:
        raise RuntimeError("all Optuna trials failed or were pruned")
    return study, outcomes


def persist_best_trial(
    *,
    config: AppConfig,
    paths: ProjectPaths,
    split: DatasetSplit,
    study: optuna.Study,
    outcomes: dict[int, TrialOutcome],
) -> BestTrialResult:
    best = study.best_trial
    if best.value is None:
        raise RuntimeError("best trial does not have an objective value")
    outcome = outcomes.get(best.number)
    if outcome is None:
        checkpoint = best.user_attrs.get("checkpoint")
        training_scores = best.user_attrs.get("training_scores")
        if not isinstance(checkpoint, str) or not isinstance(training_scores, list):
            raise RuntimeError("best trial outcome is not available in this run")
        outcome = TrialOutcome(
            validation_scores=[],
            training_scores=[float(score) for score in training_scores],
            checkpoint=Path(checkpoint),
        )
    threshold = float(
        np.percentile(
            outcome.training_scores,
            config.part.optuna_settings.threshold.percentile,
        )
    )
    target_checkpoint = paths.checkpoint(config.model)
    target_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    temporary_checkpoint = target_checkpoint.with_suffix(".ckpt.tmp")
    shutil.copy2(outcome.checkpoint, temporary_checkpoint)
    _attach_checkpoint_metadata(
        temporary_checkpoint,
        model=config.model,
        threshold=threshold,
    )
    temporary_checkpoint.replace(target_checkpoint)
    write_threshold(paths.model_config(config.model), threshold)
    result = BestTrialResult(
        model=config.model,
        trial_number=best.number,
        parameters=best.params,
        objective=float(best.value),
        checkpoint=str(target_checkpoint.relative_to(paths.root)),
        score_contract=ScoreContract(),
        threshold=threshold,
        train_sources=list(split.train_sources),
        validation_sources=list(split.validation_sources),
        seed=config.part.optuna_settings.execution.seed,
        dependencies=package_versions(),
    )
    result.write_json(paths.study_dir(config.model) / "best_trial.json")
    return result


def _attach_checkpoint_metadata(path: Path, *, model: str, threshold: float) -> None:
    import torch

    payload = torch.load(path, map_location="cpu", weights_only=False)
    payload["visual_inspection"] = {
        "model": model,
        "score_source": "supersimplenet.pred_score",
        "anomalib_post_processor": False,
        "threshold": threshold,
    }
    torch.save(payload, path)


def restart_training(paths: ProjectPaths, model: str) -> None:
    paths.remove_model_artifact(paths.study_dir(model), expected=paths.study_dir(model))
    paths.remove_model_artifact(
        paths.checkpoint(model), expected=paths.checkpoint(model)
    )


def link_dataset(images: Sequence[Path], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for index, source in enumerate(images):
        target = destination / f"{index:06d}_{source.name}"
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)


class AnomalibTrialRunner:
    """Actual Anomalib runner; tests replace this boundary with a lightweight double."""

    def __init__(
        self, work_dir: Path, device: DeviceSelection, config: AppConfig | None = None
    ):
        self.work_dir = work_dir
        self.device = device
        self.config = config

    def __call__(
        self,
        parameters: TrialParameters,
        split: DatasetSplit,
        trial: optuna.Trial,
    ) -> TrialOutcome:
        from anomalib.data import Folder
        from anomalib.engine import Engine

        trial_dir = self.work_dir / f"trial-{trial.number:04d}"
        if trial_dir.exists():
            shutil.rmtree(trial_dir)
        train_dir = trial_dir / "train"
        validation_dir = trial_dir / "validation"
        link_dataset(split.train_images, train_dir)
        link_dataset(split.validation_images, validation_dir)
        datamodule = Folder(
            name=f"visual-inspection-{trial.number}",
            normal_dir=train_dir,
            normal_test_dir=validation_dir,
            train_batch_size=parameters.batch_size,
            eval_batch_size=parameters.batch_size,
            num_workers=0,
            train_augmentations=(
                AnomalibTrainingAugmentation(self.config.part.augmentation)
                if self.config is not None
                else None
            ),
            val_augmentations=None,
            test_augmentations=None,
            val_split_mode="from_test",
            val_split_ratio=1.0,
            seed=42,
        )
        model = create_supersimplenet(
            layers=parameters.feature_layers,
            image_size=parameters.image_size,
            learning_rate_multiplier=parameters.learning_rate_multiplier,
        )
        pruning = self.config.part.optuna_settings if self.config is not None else None
        engine = Engine(
            callbacks=(
                [
                    create_pruning_callback(
                        trial,
                        percentile=pruning.normal_only.percentile,
                        interval_epochs=pruning.pruner.interval_epochs,
                    )
                ]
                if pruning is not None
                else None
            ),
            max_epochs=parameters.epochs,
            accelerator="gpu" if self.device.device == "cuda" else "cpu",
            devices=1,
            default_root_dir=trial_dir,
            logger=False,
        )
        engine.fit(model, datamodule=datamodule)
        checkpoint = trial_dir / "model.ckpt"
        engine.trainer.save_checkpoint(checkpoint)
        validation_predictions = engine.predict(
            model=model, data_path=validation_dir, return_predictions=True
        )
        training_predictions = engine.predict(
            model=model, data_path=train_dir, return_predictions=True
        )
        return TrialOutcome(
            validation_scores=extract_predictions(validation_predictions or []),
            training_scores=extract_predictions(training_predictions or []),
            checkpoint=checkpoint,
        )
