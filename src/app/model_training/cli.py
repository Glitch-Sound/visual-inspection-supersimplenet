"""Model training command entry point."""

from __future__ import annotations

import os

import optuna
import typer
from rich.console import Console
from rich.table import Table

from app.common.cli import _run, show_stage
from app.common.config import load_config, preparation_fingerprint
from app.common.contracts import (
    BestTrialResult,
    TrialParametersContract,
    load_preparation_manifest,
)
from app.common.model_adapter import BACKBONE_NAME
from app.common.paths import ProjectPaths
from app.common.runtime import RunRecorder
from app.model_training.artifacts import persist_best_trial, restart_training
from app.model_training.search import (
    TrialParameters,
    create_study,
    run_search,
    split_by_source,
)
from app.model_training.trainer import AnomalibTrialRunner


def format_training_summary(result: BestTrialResult) -> str:
    return f"暫定探索指標={result.objective} threshold={result.threshold}"


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
    show_stage(f"試行 {trial.number + 1} {status}{metric}")


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
                if restart:
                    restart_training(paths, model, selected.id)
                study_dir = paths.study_dir(model, selected.id)
                show_stage(f"グループ {selected.id}: Optuna 探索を実行")
                study = create_study(config, selected, study_dir / "study.db")
                existing = len(study.trials)
                total = selected.optuna_settings.execution.trials
                show_stage(
                    f"探索条件: バックボーン={BACKBONE_NAME} "
                    f"学習画像={len(split.train_images)} 検証画像={len(split.validation_images)} "
                    f"既存試行={existing} 今回の試行={max(0, total - existing)}"
                )
                runner = AnomalibTrialRunner(
                    study_dir / "trials", recorder.device, selected
                )
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
                result = persist_best_trial(
                    config=config,
                    group=selected,
                    paths=paths,
                    split=split,
                    study=study,
                    outcomes=outcomes,
                )
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
                raise ValueError(f"group {selected.id} failed: {error}") from error
            except Exception as error:
                raise RuntimeError(f"group {selected.id} failed: {error}") from error
        return "; ".join(summaries)

    _run("train", model, action, needs_device=True)


def train_cli() -> None:
    typer.run(_train_command)
