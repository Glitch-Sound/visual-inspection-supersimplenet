"""Publish one complete group training result without restoring old artifacts."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from uuid import uuid4

import numpy as np
import optuna

from app.common.config import AppConfig, GroupConfig, write_threshold
from app.common.contracts import (
    BestTrialResult,
    ScoreContract,
    SyntheticAnomalyContract,
    TrialParametersContract,
)
from app.common.paths import ProjectPaths
from app.common.runtime import package_versions
from app.model_training.search import DatasetSplit, TrialOutcome


def new_training_stage(paths: ProjectPaths, model: str, group: int) -> Path:
    target = paths.study_dir(model, group)
    target.parent.mkdir(parents=True, exist_ok=True)
    prefix = f".{target.name}-stage-"
    for stale in target.parent.iterdir():
        if stale.name.startswith(prefix) and re.fullmatch(
            r"[0-9a-f]{32}", stale.name[len(prefix) :]
        ):
            if stale.is_symlink() or not stale.is_dir():
                raise ValueError(f"invalid training temporary area: {stale}")
            shutil.rmtree(stale)
    checkpoint = paths.checkpoint(model, group)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_prefix = f".{checkpoint.name}-stage-"
    for stale in checkpoint.parent.iterdir():
        if stale.name.startswith(checkpoint_prefix) and re.fullmatch(
            r"[0-9a-f]{32}", stale.name[len(checkpoint_prefix) :]
        ):
            if stale.is_symlink() or not stale.is_file():
                raise ValueError(f"invalid checkpoint temporary file: {stale}")
            stale.unlink()
    stage = target.with_name(f"{prefix}{uuid4().hex}")
    stage.mkdir()
    return stage


def persist_best_trial(
    *,
    config: AppConfig,
    group: GroupConfig,
    paths: ProjectPaths,
    split: DatasetSplit,
    study: optuna.Study,
    outcomes: dict[int, TrialOutcome],
    study_dir: Path,
    best_trial: optuna.trial.FrozenTrial | None = None,
) -> BestTrialResult:
    best = study.best_trial if best_trial is None else best_trial
    if best.value is None:
        raise RuntimeError("best trial does not have an objective value")
    outcome = outcomes.get(best.number)
    if outcome is None:
        raise RuntimeError("best trial outcome is not available in this run")
    threshold = float(
        np.percentile(
            outcome.training_scores, group.optuna_settings.threshold.percentile
        )
    )
    target_checkpoint = paths.checkpoint(config.model, group.id)
    target_study = paths.study_dir(config.model, group.id)
    if study_dir.parent != target_study.parent or not study_dir.name.startswith(
        f".{target_study.name}-stage-"
    ):
        raise ValueError(f"invalid training stage: {study_dir}")
    checkpoint_stage = target_checkpoint.with_name(
        f".{target_checkpoint.name}-stage-{uuid4().hex}"
    )
    try:
        shutil.copy2(outcome.checkpoint, checkpoint_stage)
        _attach_checkpoint_metadata(
            checkpoint_stage,
            model=config.model,
            group=group.id,
            threshold=threshold,
            synthetic_anomaly=group.synthetic_anomaly.model_dump(),
        )
        result = BestTrialResult(
            model=config.model,
            group=group.id,
            range_ids=group.range_ids,
            trial_number=best.number,
            parameters=_trial_parameters_contract(best.params),
            objective=float(best.value),
            checkpoint=str(target_checkpoint.relative_to(paths.root)),
            score_contract=ScoreContract(),
            threshold=threshold,
            synthetic_anomaly=SyntheticAnomalyContract.model_validate(
                group.synthetic_anomaly.model_dump()
            ),
            train_sources=list(split.train_sources),
            validation_sources=list(split.validation_sources),
            seed=group.optuna_settings.execution.seed,
            dependencies=package_versions(),
        )
        result.write_json(study_dir / "best_trial.json")
        if target_study.exists():
            paths.remove_model_artifact(target_study, expected=target_study)
        study_dir.replace(target_study)
        if target_checkpoint.exists():
            paths.remove_model_artifact(target_checkpoint, expected=target_checkpoint)
        checkpoint_stage.replace(target_checkpoint)
        write_threshold(paths.model_config(config.model), threshold, group=group.id)
        return result
    finally:
        if study_dir.exists():
            shutil.rmtree(study_dir)
        checkpoint_stage.unlink(missing_ok=True)


def _trial_parameters_contract(
    parameters: dict[str, object],
) -> TrialParametersContract:
    normalized = dict(parameters)
    layers = normalized.get("feature_layers")
    if isinstance(layers, str):
        try:
            normalized["feature_layers"] = json.loads(layers)
        except json.JSONDecodeError as error:
            raise ValueError("feature_layers must contain valid JSON") from error
    return TrialParametersContract.model_validate(normalized)


def _attach_checkpoint_metadata(
    path: Path,
    *,
    model: str,
    group: int,
    threshold: float,
    synthetic_anomaly: dict[str, object],
) -> None:
    import torch

    payload = torch.load(path, map_location="cpu", weights_only=False)
    payload["visual_inspection"] = {
        "model": model,
        "group": group,
        "score_source": "supersimplenet.pred_score",
        "anomalib_post_processor": False,
        "threshold": threshold,
        "synthetic_anomaly": synthetic_anomaly,
    }
    torch.save(payload, path)
