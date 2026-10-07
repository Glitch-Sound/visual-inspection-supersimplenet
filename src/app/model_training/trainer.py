"""Anomalib trial execution and pretrained cache handling."""

from __future__ import annotations

import os
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import optuna

from app.common.config import AppConfig
from app.common.model_adapter import create_supersimplenet
from app.common.runtime import DeviceSelection
from app.model_training.augmentation import AnomalibTrainingAugmentation
from app.model_training.search import DatasetSplit, TrialOutcome, TrialParameters


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
            val_split_mode="same_as_test",
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


def ensure_cached(path: Path, fetch: Any) -> Path:
    """Populate a pretrained artifact once without exposing a partial download."""

    if path.is_file():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        fetch(temporary)
        if not temporary.is_file():
            raise OSError("pretrained fetcher did not create the requested artifact")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


def extract_predictions(prediction_batches: list[Any]) -> list[float]:
    """Extract raw sigmoid ``pred_score`` values from Anomalib predictions."""

    scores: list[float] = []
    for batch in prediction_batches:
        values = getattr(batch, "pred_score", None)
        if values is None and isinstance(batch, dict):
            values = batch.get("pred_score")
        if values is None:
            raise ValueError("Anomalib prediction does not contain pred_score")
        if hasattr(values, "detach"):
            values = values.detach().cpu().reshape(-1).tolist()
        elif not isinstance(values, list):
            values = [values]
        scores.extend(float(value) for value in values)
    return scores
