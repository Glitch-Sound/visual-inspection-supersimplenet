"""Model evaluation command entry point."""

from __future__ import annotations

import typer

from app.common.artifact_transaction import recover_artifact_transaction
from app.common.cli import ExitCode, _run, show_stage
from app.common.config import load_config
from app.common.contracts import BestTrialResult
from app.common.paths import ProjectPaths
from app.common.runtime import RunRecorder
from app.model_evaluation.evaluation import (
    evaluate_model,
    restart_evaluation,
    validate_best_trial_contract,
)
from app.model_evaluation.predictor import CheckpointPredictor


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

        results = evaluate_model(
            config,
            paths,
            predictor=predictor,
            finish_runtime=lambda: recorder.finish(ExitCode.SUCCESS),
            record_warning=recorder.warnings.append,
            record_error=recorder.errors.append,
            on_threshold_selected=show_selected_threshold,
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
