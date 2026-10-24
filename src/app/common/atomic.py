"""Shared staged directory replacement for generated artifacts."""

from __future__ import annotations

import re
import shutil
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4


def publish_staged_directory(
    stage: Path, target: Path, *, backup: Path | None = None
) -> None:
    """Move a complete directory into place, optionally retaining the old one."""

    if stage.is_symlink() or not stage.is_dir():
        raise ValueError(f"invalid staged directory: {stage}")
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise ValueError(f"invalid target directory: {target}")
    if backup is None:
        if target.exists():
            shutil.rmtree(target)
        stage.replace(target)
        return
    if backup.exists() or backup.is_symlink():
        raise ValueError(f"backup already exists: {backup}")
    had_target = target.exists()
    if had_target:
        target.replace(backup)
    try:
        stage.replace(target)
    except BaseException:
        if had_target and not target.exists() and backup.exists():
            backup.replace(target)
        raise
    if had_target:
        shutil.rmtree(backup)


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
