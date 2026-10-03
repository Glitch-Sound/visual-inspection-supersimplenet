"""Recovery helpers for model-scoped directory replacement."""

from __future__ import annotations

import shutil
from pathlib import Path


def recover_directory_swap(target: Path) -> Path:
    """Recover or clean a backup left by an interrupted directory swap."""

    backup = target.with_name(f".{target.name}.backup")
    if backup.exists():
        if target.exists():
            shutil.rmtree(backup)
        else:
            backup.replace(target)
    return backup
