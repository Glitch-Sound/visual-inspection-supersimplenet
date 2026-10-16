"""Model training command entry point."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import optuna
import typer
from rich.console import Console
from rich.table import Table

from app.common.cli import _run, show_stage
from app.common.config import load_config, preparation_fingerprint
from app.common.contracts import (
    BestTrialResult,
    FoldRecord,
    SourceScore,
    TrialParametersContract,
    load_preparation_manifest,
)
from app.common.model_adapter import BACKBONE_NAME
from app.common.paths import ProjectPaths
from app.common.runtime import RunRecorder
from app.model_training.artifacts import (
    _trial_parameters_contract,
    finish_restart,
    persist_best_trial,
    restart_training,
    restore_restart,
)
from app.model_training.search import (
    TrialParameters,
    all_prepared_images,
    create_study,
    cross_validation_splits,
    run_search,
    split_by_source,
)
from app.model_training.synthetic_validation import create_synthetic_validation
from app.model_training.trainer import AnomalibTrialRunner, fit_selected_parameters


def format_training_summary(result: BestTrialResult) -> str:
    name = getattr(result, "objective_name", "normal_percentile")
    if name == "normal_percentile":
        return f"暫定探索指標={result.objective} threshold={result.threshold}"
    return f"擬似AUROC暫定探索指標={result.objective} threshold={result.threshold}"


def show_trial_conditions(
    title: str, parameters: TrialParameters | TrialParametersContract
) -> None:
    """Show the selected trial conditions as a two-column stderr table."""
    table = Table(title=title)
    table.add_column("条件")
    table.add_column("値")
    for label, value in (
        ("学習率倍率", parameters.learning_rate_multiplier),
        ("バッチサイズ", parameters.batch_size),
        ("エポック数", parameters.epochs),
        ("特徴層", ", ".join(parameters.feature_layers)),
        ("前処理画像サイズ", f"{parameters.image_size} px"),
    ):
        table.add_row(label, str(value))
    Console(stderr=True).print(table)


def show_trial_outcome(trial: optuna.trial.FrozenTrial) -> None:
    labels = {
        optuna.trial.TrialState.COMPLETE: "完了",
        optuna.trial.TrialState.PRUNED: "枝刈り",
        optuna.trial.TrialState.FAIL: "失敗",
    }
    status = labels.get(trial.state, trial.state.name)
    metric = (
        f" 暫定探索指標={trial.value}"
        if trial.state == optuna.trial.TrialState.COMPLETE
        else ""
    )
    reason = trial.user_attrs.get("failure_reason")
    detail = (
        f" 理由={reason}"
        if trial.state == optuna.trial.TrialState.FAIL and reason
        else ""
    )
    show_stage(f"試行 {trial.number + 1} {status}{metric}{detail}")


def _train_command(
    model: str = typer.Option(..., "--model", help="処理対象の型番"),
    group: int | None = typer.Option(None, "--group", help="処理対象のグループID"),
    restart: bool = typer.Option(False, "--restart", help="探索とモデルを再生成する"),
) -> None:
    """型番別・グループ別モデルを学習する。"""

    def action(paths: ProjectPaths, recorder: RunRecorder) -> str:
        show_stage("設定読込と学習入力の確認")
        config = load_config(paths.root, model)
        groups = config.part.select_groups(group)
        recorder.groups = [item.id for item in groups]
        os.environ.setdefault("TORCH_HOME", str(paths.pretrained))
        summaries: list[str] = []
        for selected in groups:
            restart_backup: Path | None = None
            try:
                prepared = paths.prepared_train(model, selected.id)
                manifest = load_preparation_manifest(
                    prepared,
                    model=config.model,
                    group=selected.id,
                    allowed_split_ids=set(selected.range_ids),
                    fingerprint=preparation_fingerprint(config, group=selected),
                )
                normal = selected.optuna_settings.normal_only
                split = split_by_source(
                    manifest, prepared, train_ratio=normal.train_ratio, seed=normal.seed
                )
                threshold_settings = selected.optuna_settings.threshold
                folds = (
                    cross_validation_splits(
                        manifest,
                        prepared,
                        folds=threshold_settings.folds or "leave_one_out",
                        seed=normal.seed,
                    )
                    if threshold_settings.method == "out_of_fold_percentile"
                    else ()
                )
                final_sources, final_images = all_prepared_images(manifest, prepared)
                if restart:
                    restart_backup = restart_training(paths, model, selected.id)
                study_dir = paths.study_dir(model, selected.id)
                show_stage(f"グループ {selected.id}: Optuna 探索を実行")
                study = create_study(config, selected, study_dir / "study.db")
                existing = len(study.trials)
                total = selected.optuna_settings.execution.trials
                show_stage(
                    f"探索条件: 目的={selected.optuna_settings.objective} "
                    f"バックボーン={BACKBONE_NAME} "
                    f"学習画像={len(split.train_images)} 検証画像={len(split.validation_images)} "
                    f"既存試行={existing} 今回の試行={max(0, total - existing)}"
                )
                runner = AnomalibTrialRunner(
                    study_dir / "trials", recorder.device, selected
                )
                study_dir.mkdir(parents=True, exist_ok=True)
                with TemporaryDirectory(prefix="synthetic-", dir=study_dir) as temp_dir:
                    try:
                        synthetic_images = create_synthetic_validation(
                            split.validation_images,
                            Path(temp_dir),
                            group=selected.id,
                            settings=selected.optuna_settings.synthetic_validation,
                        )
                    except (OSError, ValueError) as error:
                        split = replace(split, synthetic_error=str(error))
                    else:
                        split = replace(split, synthetic_images=synthetic_images)
                    study, outcomes = run_search(
                        selected,
                        split,
                        study,
                        runner,
                        on_trial_start=lambda number, parameters, total=total: (
                            show_trial_conditions(
                                f"試行 {number + 1}/{total} 開始条件", parameters
                            )
                        ),
                        on_trial_finish=show_trial_outcome,
                    )
                selected_contract = _trial_parameters_contract(study.best_trial.params)
                parameters = TrialParameters(**selected_contract.model_dump())
                fold_records: list[FoldRecord] = []
                score_records: list[SourceScore] = []
                source_by_split = {
                    part.image: source.source_image
                    for source in manifest.sources
                    for part in source.splits
                }
                for fold_number, fold in enumerate(folds, start=1):
                    show_stage(
                        f"グループ {selected.id}: 交差検証 {fold_number}/{len(folds)}"
                    )
                    try:
                        _, scores = fit_selected_parameters(
                            parameters,
                            train_images=fold.train_images,
                            validation_images=fold.validation_images,
                            work_dir=study_dir
                            / "cross_validation"
                            / f"fold-{fold_number:04d}",
                            device=recorder.device,
                            group=selected,
                            seed=selected.optuna_settings.execution.seed + fold_number,
                        )
                        fold_records.append(
                            FoldRecord(
                                train_sources=list(fold.train_sources),
                                validation_sources=list(fold.validation_sources),
                            )
                        )
                        for image, score in zip(
                            fold.validation_images, scores, strict=True
                        ):
                            score_records.append(
                                SourceScore(
                                    source_image=source_by_split[image.name],
                                    split_image=image.name,
                                    score=score,
                                )
                            )
                    except (ValueError, KeyError) as error:
                        raise RuntimeError(
                            f"cross-validation fold {fold_number} failed: {error}"
                        ) from error
                show_stage(f"グループ {selected.id}: 全正常データで最終学習")
                final_checkpoint, final_training_scores = fit_selected_parameters(
                    parameters,
                    train_images=final_images,
                    validation_images=final_images,
                    work_dir=study_dir / "final_refit",
                    device=recorder.device,
                    group=selected,
                    seed=selected.optuna_settings.execution.seed,
                )
                if threshold_settings.method == "training_percentile" and (
                    len(final_training_scores) != len(final_images)
                    or not np.isfinite(final_training_scores).all()
                    or any(
                        score < 0.0 or score > 1.0 for score in final_training_scores
                    )
                ):
                    raise ValueError(
                        "final training scores must match all images and be finite in [0, 1]"
                    )
                result = persist_best_trial(
                    config=config,
                    group=selected,
                    paths=paths,
                    split=split,
                    study=study,
                    outcomes=outcomes,
                    final_checkpoint=final_checkpoint,
                    final_training_scores=final_training_scores,
                    final_train_sources=final_sources,
                    cross_validation=fold_records,
                    score_by_source=score_records,
                    record_warning=recorder.warnings.append,
                )
                if not finish_restart(paths, restart_backup):
                    show_stage(f"グループ {selected.id}: 旧探索履歴の整理を後で再試行")
                restart_backup = None
                show_trial_conditions(
                    f"グループ {selected.id} 最良試行 {result.trial_number + 1} の条件",
                    result.parameters,
                )
                show_stage(
                    f"グループ {selected.id} 学習完了: 試行数={len(study.trials)} "
                    f"暫定閾値={result.threshold} 保存先={paths.checkpoint(model, selected.id)}"
                )
                summaries.append(
                    f"group {selected.id}: {format_training_summary(result)}"
                )
                config = load_config(paths.root, model)
            except (ValueError, FileNotFoundError) as error:
                restore_restart(
                    paths, paths.study_dir(model, selected.id), restart_backup
                )
                raise ValueError(f"group {selected.id} failed: {error}") from error
            except Exception as error:
                restore_restart(
                    paths, paths.study_dir(model, selected.id), restart_backup
                )
                raise RuntimeError(f"group {selected.id} failed: {error}") from error
        return "; ".join(summaries)

    _run("train", model, action, needs_device=True)


def train_cli() -> None:
    typer.run(_train_command)
