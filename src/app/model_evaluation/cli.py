"""Model evaluation command entry point."""

from __future__ import annotations

import typer

from app.common.artifact_transaction import recover_artifact_transaction
from app.common.cli import ExitCode, _run
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
        results = evaluate_model(
            config,
            paths,
            predictor=predictor,
            finish_runtime=lambda: recorder.finish(ExitCode.SUCCESS),
            record_warning=recorder.warnings.append,
            record_error=recorder.errors.append,
        )
        return f"{len(results)} source images"

    _run("test", model, action, needs_device=True)


def test_cli() -> None:
    typer.run(_test_command)
