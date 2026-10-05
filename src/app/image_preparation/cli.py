"""Image preparation command entry points."""

from __future__ import annotations

from pathlib import Path

import typer

from app.common.cli import _run
from app.common.config import load_config
from app.common.paths import ProjectPaths
from app.common.runtime import RunRecorder
from app.image_preparation.preparation import (
    alignment_warning,
    create_check_image,
    prepare_testing,
    prepare_training,
)


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


def check_cli() -> None:
    typer.run(_check_command)


def train_pre_cli() -> None:
    typer.run(_train_pre_command)


def test_pre_cli() -> None:
    typer.run(_test_pre_command)
