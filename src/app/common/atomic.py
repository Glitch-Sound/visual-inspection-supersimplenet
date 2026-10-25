"""Shared staged directory replacement for generated artifacts."""

from __future__ import annotations

import re
import shutil
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4


def publish_staged_directory(stage: Path, target: Path) -> None:
    """Replace an old directory with a complete staged directory."""

    if stage.is_symlink() or not stage.is_dir():
        raise ValueError(f"invalid staged directory: {stage}")
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise ValueError(f"invalid target directory: {target}")
    if target.exists():
        shutil.rmtree(target)
    stage.replace(target)


def replace_directory(target: Path, populate: Callable[[Path], None]) -> None:
    """Build a directory beside its target before replacing the old contents."""

    target.parent.mkdir(parents=True, exist_ok=True)
    prefix = f".{target.name}-stage-"
    for stale in target.parent.iterdir():
        if not stale.name.startswith(prefix):
            continue
        if not re.fullmatch(r"[0-9a-f]{32}", stale.name[len(prefix) :]):
            continue
        if stale.is_symlink() or not stale.is_dir():
            raise ValueError(f"invalid temporary area: {stale}")
        shutil.rmtree(stale)
    stage = target.with_name(f"{prefix}{uuid4().hex}")
    stage.mkdir()
    try:
        populate(stage)
        publish_staged_directory(stage, target)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
