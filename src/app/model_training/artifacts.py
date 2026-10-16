"""Training artifact persistence and restart."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import numpy as np
import optuna

from app.common.artifact_transaction import (
    _remove_transaction_files,
    _transaction_journal,
    _transaction_path,
    recover_artifact_transaction,
    recover_restart_backup,
)
from app.common.config import AppConfig, GroupConfig, write_threshold
from app.common.contracts import (
    BestTrialResult,
    FoldRecord,
    ScoreContract,
    SourceScore,
    SplitThreshold,
    TrialParametersContract,
)
from app.common.paths import ProjectPaths
from app.common.runtime import package_versions
from app.model_training.search import (
    DatasetSplit,
    TrialOutcome,
    select_best_trial,
    synthetic_auroc_ceiling_trial_count,
)


def persist_best_trial(
    *,
    config: AppConfig,
    group: GroupConfig,
    paths: ProjectPaths,
    split: DatasetSplit,
    study: optuna.Study,
    outcomes: dict[int, TrialOutcome],
    final_checkpoint: Path | None = None,
    final_training_scores: list[float] | None = None,
    final_train_sources: tuple[str, ...] | None = None,
    cross_validation: list[FoldRecord] | None = None,
    score_by_source: list[SourceScore] | None = None,
    record_warning: Callable[[str], None] | None = None,
) -> BestTrialResult:
    recover_artifact_transaction(paths, config.model, group.id)
    best = select_best_trial(study, group.optuna_settings.objective)
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
    threshold_settings = group.optuna_settings.threshold
    if threshold_settings.method == "out_of_fold_percentile":
        scores = [item.score for item in score_by_source or []]
        if not scores or not np.isfinite(scores).all():
            raise RuntimeError("out-of-fold scores must be nonempty and finite")
        threshold = min(
            1.0,
            float(np.percentile(scores, threshold_settings.percentile))
            + threshold_settings.margin,
        )
    else:
        if final_checkpoint is not None and final_training_scores is None:
            raise ValueError("final checkpoint training scores are required")
        training_scores = (
            final_training_scores
            if final_training_scores is not None
            else outcome.training_scores
        )
        if not training_scores or not np.isfinite(training_scores).all():
            raise ValueError("final training scores must be nonempty and finite")
        threshold = float(np.percentile(training_scores, threshold_settings.percentile))
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("calculated threshold must be in [0, 1]")
    split_thresholds: dict[str, SplitThreshold] = {}
    threshold_warnings: list[str] = []
    if threshold_settings.unit == "split":
        minimum = threshold_settings.min_score_count
        if minimum is None:
            raise ValueError("min_score_count is required for split thresholds")
        by_id: dict[int, list[float]] = {split_id: [] for split_id in group.range_ids}
        for item in score_by_source or []:
            source = Path(item.source_image)
            matching = [
                split_id
                for split_id in group.range_ids
                if item.split_image == f"{source.stem}_{split_id:02d}{source.suffix}"
            ]
            if len(matching) != 1:
                raise ValueError(
                    f"split score image does not match group range_ids: {item.split_image}"
                )
            by_id[matching[0]].append(item.score)
        for split_id in group.range_ids:
            values = by_id[split_id]
            if len(values) >= minimum:
                split_value = min(
                    1.0,
                    float(np.percentile(values, threshold_settings.percentile))
                    + threshold_settings.margin,
                )
                source_name = "calculated"
            else:
                split_value = threshold
                source_name = "group_fallback"
                warning = (
                    f"group {group.id} split {split_id}: out-of-fold score count "
                    f"{len(values)} is below min_score_count {minimum}; using group threshold"
                )
                threshold_warnings.append(warning)
                if record_warning is not None:
                    record_warning(warning)
            split_thresholds[str(split_id)] = SplitThreshold(
                value=split_value, source=source_name, score_count=len(values)
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
        shutil.copy2(final_checkpoint or outcome.checkpoint, stages["checkpoint"])
        _attach_checkpoint_metadata(
            stages["checkpoint"],
            model=config.model,
            group=group.id,
            threshold=threshold,
            threshold_unit=threshold_settings.unit,
            min_score_count=threshold_settings.min_score_count,
            split_thresholds=split_thresholds,
        )
        write_threshold(
            target_config,
            threshold,
            group=group.id,
            split_values=split_thresholds
            if threshold_settings.unit == "split"
            else None,
            destination=stages["config"],
        )
        result = BestTrialResult(
            model=config.model,
            group=group.id,
            range_ids=group.range_ids,
            trial_number=best.number,
            parameters=_trial_parameters_contract(best.params),
            objective=float(best.value),
            objective_name=group.optuna_settings.objective,
            normal_p99=best.user_attrs.get("normal_p99"),
            synthetic_auroc=best.user_attrs.get("synthetic_auroc"),
            synthetic_auroc_ceiling_trial_count=(
                synthetic_auroc_ceiling_trial_count(study)
                if group.optuna_settings.objective == "synthetic_auroc"
                else None
            ),
            synthetic_scores_summary=best.user_attrs.get("synthetic_scores_summary"),
            synthetic_validation=(
                group.optuna_settings.synthetic_validation.evaluation_contract()
            ),
            checkpoint=str(target_checkpoint.relative_to(paths.root)),
            threshold_score_model=(
                "final_checkpoint"
                if threshold_settings.method == "training_percentile"
                else "cross_validation"
            ),
            threshold_model_checkpoint=(
                str(target_checkpoint.relative_to(paths.root))
                if threshold_settings.method == "training_percentile"
                else None
            ),
            score_contract=ScoreContract(),
            threshold=threshold,
            threshold_method=threshold_settings.method,
            threshold_percentile=threshold_settings.percentile,
            threshold_margin=threshold_settings.margin,
            threshold_unit=threshold_settings.unit,
            min_score_count=threshold_settings.min_score_count,
            split_thresholds=split_thresholds,
            threshold_warnings=threshold_warnings,
            cross_validation=cross_validation or [],
            score_by_source=score_by_source or [],
            final_train_sources=list(
                final_train_sources
                if final_train_sources is not None
                else sorted(set(split.train_sources) | set(split.validation_sources))
            ),
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
    if result.synthetic_auroc_ceiling_trial_count and record_warning is not None:
        record_warning(
            f"group {group.id}: synthetic AUROC reached 1.0 in "
            f"{result.synthetic_auroc_ceiling_trial_count} completed trials; "
            "review synthetic validation conditions and real anomalies"
        )
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
    path: Path,
    *,
    model: str,
    group: int,
    threshold: float,
    threshold_unit: str = "group",
    min_score_count: int | None = None,
    split_thresholds: dict[str, SplitThreshold] | None = None,
) -> None:
    import torch

    payload = torch.load(path, map_location="cpu", weights_only=False)
    payload["visual_inspection"] = {
        "model": model,
        "group": group,
        "score_source": "supersimplenet.pred_score",
        "anomalib_post_processor": False,
        "threshold": threshold,
        "threshold_unit": threshold_unit,
        "min_score_count": min_score_count,
        "split_thresholds": {
            key: item.model_dump() for key, item in (split_thresholds or {}).items()
        },
    }
    torch.save(payload, path)


def restart_training(paths: ProjectPaths, model: str, group: int) -> Path | None:
    """Move old search history aside until the replacement is published."""
    study_dir = paths.study_dir(model, group)
    backup = study_dir.with_name(study_dir.name + ".restart-backup")
    recover_artifact_transaction(paths, model, group)
    recover_restart_backup(paths, model, group)
    if not study_dir.exists():
        return None
    study_dir.replace(backup)
    return backup


def finish_restart(paths: ProjectPaths, backup: Path | None) -> bool:
    if backup is not None and backup.exists():
        try:
            paths.remove_model_artifact(backup, expected=backup)
        except OSError:
            return False
    return True


def restore_restart(paths: ProjectPaths, study_dir: Path, backup: Path | None) -> None:
    if backup is not None and backup.exists():
        paths.remove_model_artifact(study_dir, expected=study_dir)
        backup.replace(study_dir)
