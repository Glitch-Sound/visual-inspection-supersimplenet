"""Command-line entry points for the visual inspection workflow."""

import json
import os
from collections.abc import Callable
from enum import IntEnum
from pathlib import Path
from typing import Any

import typer

from app.config import load_config
from app.contracts import PreparationManifest
from app.evaluation import evaluate_model, restart_evaluation
from app.modeling import CheckpointPredictor
from app.paths import ProjectPaths
from app.preparation import create_check_image, prepare_testing, prepare_training
from app.runtime import DeviceSelection, RunRecorder, select_device
from app.training import (
    AnomalibTrialRunner,
    create_study,
    format_training_summary,
    persist_best_trial,
    restart_training,
    run_search,
    split_by_source,
)


class ExitCode(IntEnum):
    """Stable process exit codes shared by every command."""

    SUCCESS = 0
    INPUT_ERROR = 2
    PROCESSING_ERROR = 3


def _run(
    command: str,
    model: str,
    action: Callable[[ProjectPaths, RunRecorder], Any],
    *,
    needs_device: bool = False,
) -> None:
    paths = ProjectPaths(Path.cwd())
    device = (
        select_device()
        if needs_device
        else DeviceSelection("cpu", "CPU", "not required")
    )
    recorder = RunRecorder(command, model, device)
    try:
        result = action(paths, recorder)
    except (ValueError, FileNotFoundError) as error:
        recorder.errors.append(str(error))
        typer.echo(
            json.dumps(recorder.finish(ExitCode.INPUT_ERROR), ensure_ascii=False)
        )
        raise typer.Exit(ExitCode.INPUT_ERROR) from error
    except Exception as error:
        recorder.errors.append(str(error))
        typer.echo(
            json.dumps(recorder.finish(ExitCode.PROCESSING_ERROR), ensure_ascii=False)
        )
        raise typer.Exit(ExitCode.PROCESSING_ERROR) from error
    metadata = recorder.finish(ExitCode.SUCCESS)
    if result is not None:
        metadata["result"] = str(result)
    typer.echo(json.dumps(metadata, ensure_ascii=False))


def _check_command(
    model: str = typer.Option(..., "--model", help="処理対象の型番"),
) -> None:
    """分割位置を確認する。"""

    def action(paths: ProjectPaths, _recorder: RunRecorder) -> Path:
        return create_check_image(load_config(paths.root, model), paths)

    _run("check", model, action)


def _train_pre_command(
    model: str = typer.Option(..., "--model", help="処理対象の型番"),
) -> None:
    """学習画像を位置合わせして分割する。"""

    def action(paths: ProjectPaths, recorder: RunRecorder) -> str:
        manifest = prepare_training(load_config(paths.root, model), paths)
        recorder.warnings.extend(
            str(item) for item in manifest.excluded if item.get("reason") != "blacklist"
        )
        return str(paths.prepared_train(model))

    _run("train-pre", model, action)


def _train_command(
    model: str = typer.Option(..., "--model", help="処理対象の型番"),
    restart: bool = typer.Option(False, "--restart", help="探索とモデルを再生成する"),
) -> None:
    """型番別モデルを学習する。"""

    def action(paths: ProjectPaths, recorder: RunRecorder) -> str:
        config = load_config(paths.root, model)
        os.environ.setdefault("TORCH_HOME", str(paths.pretrained))
        if restart:
            restart_training(paths, model)
        prepared = paths.prepared_train(model)
        manifest = PreparationManifest.read_json(prepared / "manifest.json")
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


def _test_pre_command(
    model: str = typer.Option(..., "--model", help="処理対象の型番"),
) -> None:
    """試験画像を位置合わせして分割する。"""

    def action(paths: ProjectPaths, recorder: RunRecorder) -> str:
        manifest = prepare_testing(load_config(paths.root, model), paths)
        recorder.warnings.extend(
            source.alignment.reason or "alignment_failed"
            for source in manifest.sources
            if source.alignment.status != "aligned"
        )
        return str(paths.prepared_test(model))

    _run("test-pre", model, action)


def _test_command(
    model: str = typer.Option(..., "--model", help="処理対象の型番"),
    restart: bool = typer.Option(False, "--restart", help="検査結果を再生成する"),
) -> None:
    """型番別モデルで試験画像を検査する。"""

    def action(paths: ProjectPaths, recorder: RunRecorder) -> str:
        config = load_config(paths.root, model)
        if restart:
            restart_evaluation(paths, model)
        best = json.loads(
            (paths.study_dir(model) / "best_trial.json").read_text(encoding="utf-8")
        )
        params = best["parameters"]
        layers = params["feature_layers"]
        if isinstance(layers, str):
            layers = json.loads(layers)
        predictor = CheckpointPredictor(
            paths.checkpoint(model),
            layers=layers,
            image_size=int(params["image_size"]),
            learning_rate_multiplier=float(params["learning_rate_multiplier"]),
            device=recorder.device.device,
        )
        results = evaluate_model(
            config,
            paths,
            predictor=predictor,
            runtime=recorder.finish(ExitCode.SUCCESS),
        )
        return f"{len(results)} source images"

    _run("test", model, action, needs_device=True)


def check_cli() -> None:
    typer.run(_check_command)


def train_pre_cli() -> None:
    typer.run(_train_pre_command)


def train_cli() -> None:
    typer.run(_train_command)


def test_pre_cli() -> None:
    typer.run(_test_pre_command)


def test_cli() -> None:
    typer.run(_test_command)
