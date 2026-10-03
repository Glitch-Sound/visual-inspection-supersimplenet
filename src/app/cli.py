"""Command-line entry points for the visual inspection workflow."""

import json
import os
from collections.abc import Callable
from enum import IntEnum
from pathlib import Path
from typing import Any

import typer

from app.config import load_config
from app.contracts import BestTrialResult, PreparationManifest
from app.evaluation import (
    evaluate_model,
    restart_evaluation,
    validate_best_trial_contract,
)
from app.modeling import CheckpointPredictor
from app.paths import ProjectPaths
from app.preparation import (
    alignment_warning,
    create_check_image,
    prepare_testing,
    prepare_training,
)
from app.runtime import DeviceSelection, RunRecorder, select_device
from app.training import (
    AnomalibTrialRunner,
    create_study,
    format_training_summary,
    persist_best_trial,
    recover_artifact_transaction,
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
        typer.echo(recorder.finish(ExitCode.INPUT_ERROR).model_dump_json())
        raise typer.Exit(ExitCode.INPUT_ERROR) from error
    except Exception as error:
        recorder.errors.append(str(error))
        typer.echo(recorder.finish(ExitCode.PROCESSING_ERROR).model_dump_json())
        raise typer.Exit(ExitCode.PROCESSING_ERROR) from error
    metadata = recorder.finish(ExitCode.SUCCESS).model_dump(mode="json")
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
            alignment_warning(
                str(item["source_image"]), str(item["reason"]), testing=False
            )
            for item in manifest.excluded
            if item.get("reason") != "blacklist"
        )
        return str(paths.prepared_train(model))

    _run("train-pre", model, action)


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


def _test_pre_command(
    model: str = typer.Option(..., "--model", help="処理対象の型番"),
) -> None:
    """試験画像を位置合わせして分割する。"""

    def action(paths: ProjectPaths, recorder: RunRecorder) -> str:
        manifest = prepare_testing(load_config(paths.root, model), paths)
        recorder.warnings.extend(
            alignment_warning(
                source.source_image,
                source.alignment.reason or "alignment_failed",
                testing=True,
            )
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
