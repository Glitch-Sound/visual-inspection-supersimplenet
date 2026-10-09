"""Training artifact persistence and restart."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import optuna

from app.common.artifact_transaction import (
    _remove_transaction_files,
    _transaction_journal,
    _transaction_path,
    recover_artifact_transaction,
)
from app.common.config import AppConfig, GroupConfig, write_threshold
from app.common.contracts import BestTrialResult, ScoreContract, TrialParametersContract
from app.common.paths import ProjectPaths
from app.common.runtime import package_versions
from app.model_training.search import DatasetSplit, TrialOutcome


def persist_best_trial(
    *,
    config: AppConfig,
    group: GroupConfig,
    paths: ProjectPaths,
    split: DatasetSplit,
    study: optuna.Study,
    outcomes: dict[int, TrialOutcome],
) -> BestTrialResult:
    recover_artifact_transaction(paths, config.model, group.id)
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
            group.optuna_settings.threshold.percentile,
        )
    )
    target_checkpoint = paths.checkpoint(config.model, group.id)
    target_config = paths.model_config(config.model)
    target_best = paths.study_dir(config.model, group.id) / "best_trial.json"
    targets = {
        "checkpoint": target_checkpoint,
        "config": target_config,
        "best_trial": target_best,
    }
    stages = {name: _transaction_path(path, "stage") for name, path in targets.items()}
    backups = {
        name: _transaction_path(path, "backup") for name, path in targets.items()
    }
    for path in (*stages.values(), *backups.values()):
        if path.exists():
            path.unlink()

    try:
        target_checkpoint.parent.mkdir(parents=True, exist_ok=True)
        target_best.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(outcome.checkpoint, stages["checkpoint"])
        _attach_checkpoint_metadata(
            stages["checkpoint"],
            model=config.model,
            group=group.id,
            threshold=threshold,
        )
        write_threshold(
            target_config, threshold, group=group.id, destination=stages["config"]
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
            train_sources=list(split.train_sources),
            validation_sources=list(split.validation_sources),
            seed=group.optuna_settings.execution.seed,
            dependencies=package_versions(),
        )
        result.write_json(stages["best_trial"])
    except Exception:
        _remove_transaction_files((*stages.values(), *backups.values()))
        raise

    existed = {name: path.exists() for name, path in targets.items()}
    journal = _transaction_journal(paths, config.model, group.id)
    try:
        for name, path in targets.items():
            if existed[name]:
                shutil.copy2(path, backups[name])
        _write_transaction_journal(journal, existed)
        for name, target in targets.items():
            _replace_staged_artifact(stages[name], target)
        journal.unlink()
    except Exception:
        if journal.exists():
            recover_artifact_transaction(paths, config.model, group.id)
        else:
            _remove_transaction_files((*stages.values(), *backups.values()))
        raise
    _remove_transaction_files(backups.values())
    return result


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


def _write_transaction_journal(journal: Path, existed: dict[str, bool]) -> None:
    journal.parent.mkdir(parents=True, exist_ok=True)
    temporary = journal.with_suffix(journal.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps({"version": 1, "existed": existed}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(journal)
    finally:
        if temporary.exists():
            temporary.unlink()


def _replace_staged_artifact(source: Path, target: Path) -> None:
    source.replace(target)


def _attach_checkpoint_metadata(
    path: Path, *, model: str, group: int, threshold: float
) -> None:
    import torch

    payload = torch.load(path, map_location="cpu", weights_only=False)
    payload["visual_inspection"] = {
        "model": model,
        "group": group,
        "score_source": "supersimplenet.pred_score",
        "anomalib_post_processor": False,
        "threshold": threshold,
    }
    torch.save(payload, path)


def restart_training(paths: ProjectPaths, model: str, group: int) -> None:
    paths.remove_model_artifact(
        paths.study_dir(model, group), expected=paths.study_dir(model, group)
    )
    paths.remove_model_artifact(
        paths.checkpoint(model, group), expected=paths.checkpoint(model, group)
    )
