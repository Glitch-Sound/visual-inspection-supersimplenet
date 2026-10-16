"""Anomalib trial execution."""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any

import numpy as np
import optuna

from app.common.config import GroupConfig
from app.common.model_adapter import create_supersimplenet
from app.common.runtime import DeviceSelection
from app.model_training.augmentation import AnomalibTrainingAugmentation
from app.model_training.search import DatasetSplit, TrialOutcome, TrialParameters


@contextmanager
def nondeterministic_trial_algorithms() -> Iterator[None]:
    """Keep PyTorch's process-wide deterministic setting local to a trial."""
    import torch

    enabled = torch.are_deterministic_algorithms_enabled()
    warn_only = torch.is_deterministic_algorithms_warn_only_enabled()
    try:
        torch.use_deterministic_algorithms(False)
        yield
    finally:
        torch.use_deterministic_algorithms(enabled, warn_only=warn_only)


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
        self, work_dir: Path, device: DeviceSelection, group: GroupConfig | None = None
    ):
        self.work_dir = work_dir
        self.device = device
        self.group = group

    def __call__(
        self,
        parameters: TrialParameters,
        split: DatasetSplit,
        trial: optuna.Trial,
    ) -> TrialOutcome:
        from anomalib.data import Folder

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
                AnomalibTrainingAugmentation(self.group.augmentation)
                if self.group is not None
                else None
            ),
            val_augmentations=None,
            test_augmentations=None,
            val_split_mode="same_as_test",
            seed=42,
        )
        pruning = self.group.optuna_settings if self.group is not None else None
        synthetic_objective = (
            pruning is not None and pruning.objective == "synthetic_auroc"
        )
        if synthetic_objective and pruning is not None:
            from lightning.pytorch import seed_everything

            seed_everything(pruning.execution.seed + trial.number, workers=True)
        scope = (
            nondeterministic_trial_algorithms()
            if synthetic_objective
            else nullcontext()
        )
        with scope:
            return self._fit_trial(
                parameters,
                split,
                trial,
                trial_dir,
                train_dir,
                validation_dir,
                datamodule,
            )

    def _fit_trial(
        self,
        parameters: TrialParameters,
        split: DatasetSplit,
        trial: optuna.Trial,
        trial_dir: Path,
        train_dir: Path,
        validation_dir: Path,
        datamodule: Any,
    ) -> TrialOutcome:
        from anomalib.engine import Engine

        pruning = self.group.optuna_settings if self.group is not None else None
        synthetic_objective = (
            pruning is not None and pruning.objective == "synthetic_auroc"
        )
        model = create_supersimplenet(
            layers=parameters.feature_layers,
            image_size=parameters.image_size,
            learning_rate_multiplier=parameters.learning_rate_multiplier,
        )
        engine = Engine(
            callbacks=(
                [
                    create_pruning_callback(
                        trial,
                        percentile=pruning.normal_only.percentile,
                        interval_epochs=pruning.pruner.interval_epochs,
                    )
                ]
                if pruning is not None and not synthetic_objective
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
        synthetic_scores = None
        if split.synthetic_images:
            synthetic_predictions = engine.predict(
                model=model,
                data_path=split.synthetic_images[0].parent,
                return_predictions=True,
            )
            synthetic_scores = extract_predictions(synthetic_predictions or [])
        return TrialOutcome(
            validation_scores=extract_predictions(validation_predictions or []),
            training_scores=extract_predictions(training_predictions or []),
            checkpoint=checkpoint,
            synthetic_scores=synthetic_scores,
        )


def fit_selected_parameters(
    parameters: TrialParameters,
    *,
    train_images: Sequence[Path],
    validation_images: Sequence[Path],
    work_dir: Path,
    device: DeviceSelection,
    group: GroupConfig,
    seed: int,
) -> tuple[Path, list[float]]:
    """Fit selected settings and evaluate the supplied images without augmentation."""
    from anomalib.data import Folder
    from anomalib.engine import Engine
    from lightning.pytorch import seed_everything

    if not train_images or not validation_images:
        raise ValueError("selected fit requires nonempty train and validation images")
    seed_everything(seed, workers=True)
    if work_dir.exists():
        shutil.rmtree(work_dir)
    train_dir = work_dir / "train"
    validation_dir = work_dir / "validation"
    link_dataset(train_images, train_dir)
    link_dataset(validation_images, validation_dir)
    datamodule = Folder(
        name="visual-inspection-selected",
        normal_dir=train_dir,
        normal_test_dir=validation_dir,
        train_batch_size=parameters.batch_size,
        eval_batch_size=parameters.batch_size,
        num_workers=0,
        train_augmentations=AnomalibTrainingAugmentation(group.augmentation),
        val_augmentations=None,
        test_augmentations=None,
        val_split_mode="same_as_test",
        seed=seed,
    )
    model = create_supersimplenet(
        layers=parameters.feature_layers,
        image_size=parameters.image_size,
        learning_rate_multiplier=parameters.learning_rate_multiplier,
    )
    engine = Engine(
        max_epochs=parameters.epochs,
        accelerator="gpu" if device.device == "cuda" else "cpu",
        devices=1,
        default_root_dir=work_dir,
        logger=False,
    )
    engine.fit(model, datamodule=datamodule)
    checkpoint = work_dir / "model.ckpt"
    engine.trainer.save_checkpoint(checkpoint)
    model.eval()
    predictions = engine.predict(
        model=model, data_path=validation_dir, return_predictions=True
    )
    scores = extract_predictions(predictions or [])
    if len(scores) != len(validation_images):
        raise ValueError(
            f"selected fit returned {len(scores)} scores for "
            f"{len(validation_images)} validation images"
        )
    if not np.isfinite(scores).all() or any(
        score < 0.0 or score > 1.0 for score in scores
    ):
        raise ValueError("selected fit returned non-finite or out-of-range scores")
    return checkpoint, scores


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
