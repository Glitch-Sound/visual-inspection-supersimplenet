"""Model evaluation command entry point."""

from __future__ import annotations

import sys
from typing import Any

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn

from app.common.artifact_transaction import recover_artifact_transaction
from app.common.cli import ExitCode, _run, show_stage
from app.common.config import load_config
from app.common.contracts import BestTrialResult
from app.common.paths import ProjectPaths
from app.common.runtime import RunRecorder
from app.model_evaluation.evaluation import (
    evaluate_model,
    require_heatmap_range,
    restart_evaluation,
    validate_best_trial_contract,
)
from app.model_evaluation.predictor import CheckpointPredictor


class EvaluationProgress:
    """Render one source-image counter for evaluation on stderr."""

    def __init__(self) -> None:
        self._progress: Progress | None = None
        self._task_id: Any = None

    def __enter__(self) -> EvaluationProgress:
        if sys.stderr.isatty():
            self._progress = Progress(
                TextColumn("検査進捗"),
                BarColumn(),
                TextColumn("{task.completed}/{task.total}"),
                console=Console(stderr=True),
            )
            self._progress.start()
        return self

    def __exit__(self, *_args: object) -> None:
        if self._progress is not None:
            self._progress.stop()

    def update(self, processed: int, total: int) -> None:
        if self._progress is None:
            show_stage(f"検査進捗 {processed}/{total}")
            return
        if self._task_id is None:
            self._task_id = self._progress.add_task("検査進捗", total=total)
        self._progress.update(self._task_id, completed=processed, total=total)


def _test_command(
    model: str = typer.Option(..., "--model", help="処理対象の型番"),
    restart: bool = typer.Option(False, "--restart", help="検査結果を再生成する"),
) -> None:
    """型番別モデルで試験画像を検査する。"""

    def action(paths: ProjectPaths, recorder: RunRecorder) -> str:
        recover_artifact_transaction(paths, model)
        show_stage("設定読込と学習成果物の照合")
        config = load_config(paths.root, model)
        if restart:
            restart_evaluation(paths, model)
        require_heatmap_range(config)
        best = BestTrialResult.read_json(paths.study_dir(model) / "best_trial.json")
        validate_best_trial_contract(config, paths, best)
        params = best.parameters
        predictor = CheckpointPredictor(
            paths.checkpoint(model),
            layers=list(params.feature_layers),
            image_size=params.image_size,
            learning_rate_multiplier=params.learning_rate_multiplier,
            device=recorder.device.device,
        )

        def show_selected_threshold(threshold: float) -> None:
            source = (
                "暫定閾値" if config.part.inspection_threshold is None else "検査用設定"
            )
            show_stage(f"判定閾値: {threshold} ({source})")
            show_stage("分割画像を推論し、元画像単位の結果を保存")

        with EvaluationProgress() as progress:
            results = evaluate_model(
                config,
                paths,
                predictor=predictor,
                finish_runtime=lambda: recorder.finish(ExitCode.SUCCESS),
                record_warning=recorder.warnings.append,
                record_error=recorder.errors.append,
                on_threshold_selected=show_selected_threshold,
                on_progress=progress.update,
            )
        counts = {
            status: sum(result.overall_status == status for result in results)
            for status in ("normal", "anomaly", "undetermined")
        }
        show_stage(
            f"検査完了: 正常={counts['normal']} 異常={counts['anomaly']} "
            f"未判定={counts['undetermined']} 保存先={paths.results(model)}"
        )
        return f"{len(results)} source images"

    _run("test", model, action, needs_device=True)


def test_cli() -> None:
    typer.run(_test_command)
