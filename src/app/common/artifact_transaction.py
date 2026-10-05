"""Shared training artifact recovery contract."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterable
from pathlib import Path

from app.common.paths import ProjectPaths

_TRANSACTION_FILENAME = ".artifact-transaction.json"


def _transaction_path(path: Path, kind: str) -> Path:
    return path.with_name(f".{path.name}.artifact-{kind}")


def _transaction_journal(paths: ProjectPaths, model: str) -> Path:
    return paths.study_dir(model) / _TRANSACTION_FILENAME


def _remove_transaction_files(paths: Iterable[Path]) -> None:
    for path in paths:
        if path.exists():
            path.unlink()


def recover_artifact_transaction(paths: ProjectPaths, model: str) -> None:
    """Restore the previous complete training artifact set after interruption."""

    targets = {
        "checkpoint": paths.checkpoint(model),
        "config": paths.model_config(model),
        "best_trial": paths.study_dir(model) / "best_trial.json",
    }
    stages = {name: _transaction_path(path, "stage") for name, path in targets.items()}
    backups = {
        name: _transaction_path(path, "backup") for name, path in targets.items()
    }
    journal = _transaction_journal(paths, model)
    if not journal.exists():
        _remove_transaction_files(
            (
                *stages.values(),
                *backups.values(),
                journal.with_suffix(journal.suffix + ".tmp"),
            )
        )
        return
    try:
        payload = json.loads(journal.read_text(encoding="utf-8"))
        existed = payload["existed"]
        if payload.get("version") != 1 or set(existed) != set(targets):
            raise ValueError("unexpected transaction contract")
        if not all(isinstance(value, bool) for value in existed.values()):
            raise ValueError("invalid transaction existence flags")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError(f"invalid artifact transaction journal: {error}") from error

    for name, target in targets.items():
        backup = backups[name]
        if existed[name]:
            if not backup.is_file():
                raise RuntimeError(f"artifact transaction backup is missing: {name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, target)
        elif target.exists():
            target.unlink()
    journal.unlink()
    _remove_transaction_files((*stages.values(), *backups.values()))
