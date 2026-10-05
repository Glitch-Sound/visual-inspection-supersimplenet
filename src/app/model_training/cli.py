"""Model training command entry point."""

from __future__ import annotations

import os

import typer

from app.common.artifact_transaction import recover_artifact_transaction
from app.common.cli import _run
from app.common.config import load_config
from app.common.contracts import BestTrialResult, PreparationManifest
from app.common.paths import ProjectPaths
from app.common.runtime import RunRecorder
from app.model_training.artifacts import persist_best_trial, restart_training
from app.model_training.search import create_study, run_search, split_by_source
from app.model_training.trainer import AnomalibTrialRunner


def format_training_summary(result: BestTrialResult) -> str:
    return f"暫定探索指標={result.objective} threshold={result.threshold}"


def _train_command(
    model: str = typer.Option(..., "--model", help="処理対象の型番"),
    restart: bool = typer.Option(False, "--restart", help="探索とモデルを再生成する"),
) -> None:
    """型番別モデルを学習する。"""

    def action(paths: ProjectPaths, recorder: RunRecorder) -> str:
        recover_artifact_transaction(paths, model)
        config = load_config(paths.root, model)
        os.environ.setdefault("TORCH_HOME", str(paths.pretrained))
        if restart:
            restart_training(paths, model)
        prepared = paths.prepared_train(model)
        manifest = PreparationManifest.read_json(prepared / "manifest.json")
        if manifest.model != config.model:
            raise ValueError(
                f"training manifest model mismatch: expected {config.model}, "
                f"got {manifest.model}"
            )
        normal = config.part.optuna_settings.normal_only
        split = split_by_source(
            manifest, prepared, train_ratio=normal.train_ratio, seed=normal.seed
        )
        study_dir = paths.study_dir(model)
        study = create_study(config, study_dir / "study.db")
        runner = AnomalibTrialRunner(study_dir / "trials", recorder.device, config)
        study, outcomes = run_search(config, split, study, runner)
        result = persist_best_trial(
            config=config,
            paths=paths,
            split=split,
            study=study,
            outcomes=outcomes,
        )
        return format_training_summary(result)

    _run("train", model, action, needs_device=True)


def train_cli() -> None:
    typer.run(_train_command)
