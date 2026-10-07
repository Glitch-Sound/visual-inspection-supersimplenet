"""Shared command execution and exit codes."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from enum import IntEnum
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn

from app.common.paths import ProjectPaths
from app.common.runtime import DeviceSelection, RunRecorder, select_device


class ExitCode(IntEnum):
    """Stable process exit codes shared by every command."""

    SUCCESS = 0
    INPUT_ERROR = 2
    PROCESSING_ERROR = 3


def show_stage(message: str) -> None:
    typer.echo(message, err=True)


class PreparationProgress:
    """Render one source-image counter on stderr."""

    def __init__(self) -> None:
        self._progress: Progress | None = None
        self._task_id: Any = None

    def __enter__(self) -> PreparationProgress:
        if sys.stderr.isatty():
            self._progress = Progress(
                TextColumn("準備進捗"),
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
            show_stage(f"準備進捗 {processed}/{total}")
            return
        if self._task_id is None:
            self._task_id = self._progress.add_task("準備進捗", total=total)
        self._progress.update(self._task_id, completed=processed, total=total)


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
    show_stage(f"開始: {command} 型番={model}")
    if needs_device:
        show_stage(f"使用デバイス: {device.device} ({device.name}; {device.reason})")
    try:
        result = action(paths, recorder)
    except (ValueError, FileNotFoundError) as error:
        recorder.errors.append(str(error))
        metadata = recorder.finish(ExitCode.INPUT_ERROR)
        show_stage(f"入力不備: {error}")
        show_stage(f"終了: {command} 入力不備 ({metadata.duration_seconds:.2f}秒)")
        typer.echo(metadata.model_dump_json())
        raise typer.Exit(ExitCode.INPUT_ERROR) from error
    except Exception as error:
        recorder.errors.append(str(error))
        metadata = recorder.finish(ExitCode.PROCESSING_ERROR)
        show_stage(f"処理失敗: {error}")
        show_stage(f"終了: {command} 未完了 ({metadata.duration_seconds:.2f}秒)")
        typer.echo(metadata.model_dump_json())
        raise typer.Exit(ExitCode.PROCESSING_ERROR) from error
    completed = recorder.finish(ExitCode.SUCCESS)
    for warning in completed.warnings:
        show_stage(f"警告: {warning}")
    for error in completed.errors:
        show_stage(f"エラー: {error}")
    outcome = (
        f"処理完了・一部エラー={len(completed.errors)}" if completed.errors else "成功"
    )
    show_stage(f"終了: {command} {outcome} ({completed.duration_seconds:.2f}秒)")
    metadata = completed.model_dump(mode="json")
    if result is not None:
        metadata["result"] = str(result)
    typer.echo(json.dumps(metadata, ensure_ascii=False))
