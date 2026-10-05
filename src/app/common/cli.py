"""Shared command execution and exit codes."""

from __future__ import annotations

import json
from collections.abc import Callable
from enum import IntEnum
from pathlib import Path
from typing import Any

import typer

from app.common.paths import ProjectPaths
from app.common.runtime import DeviceSelection, RunRecorder, select_device


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
