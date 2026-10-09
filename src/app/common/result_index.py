"""Atomic publication and safe lookup of group inspection results."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from uuid import uuid4

from app.common.paths import ProjectPaths, ensure_no_symlink_components

_RUN_ID = re.compile(r"^[0-9a-f]{32}$")


def _result_root(paths: ProjectPaths, model: str) -> Path:
    root = paths.results(model)
    ensure_no_symlink_components(paths.root, root)
    return root


def read_current(
    paths: ProjectPaths, model: str, *, allowed_group_ids: set[int] | None = None
) -> dict[int, str]:
    root = _result_root(paths, model)
    current = root / "current.json"
    if current.is_symlink():
        raise ValueError("current.json must not be a symlink")
    if not current.exists():
        return {}
    try:
        payload = json.loads(current.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid current.json: {error}") from error
    if (
        not isinstance(payload, dict)
        or payload.get("version") != 1
        or not isinstance(payload.get("groups"), dict)
    ):
        raise ValueError("invalid current.json version or groups")
    result: dict[int, str] = {}
    for key, value in payload["groups"].items():
        if not isinstance(key, str) or not key.isdecimal() or str(int(key)) != key:
            raise ValueError(f"invalid current.json group id: {key!r}")
        group = int(key)
        if allowed_group_ids is not None and group not in allowed_group_ids:
            raise ValueError(f"current.json references unknown group {group}")
        if not isinstance(value, str):
            raise ValueError(f"invalid current.json path for group {group}")
        relative = Path(value)
        parts = relative.parts
        if (
            len(parts) != 3
            or parts[0] != "generations"
            or not _RUN_ID.fullmatch(parts[1])
            or parts[2] != f"group_{group}"
        ):
            raise ValueError(f"invalid current.json path for group {group}: {value!r}")
        target = root / relative
        ensure_no_symlink_components(root, target)
        if not target.is_dir():
            raise ValueError(f"current.json target missing for group {group}: {value}")
        result[group] = value
    return result


def create_generation(paths: ProjectPaths, model: str) -> Path:
    root = _result_root(paths, model)
    generations = root / "generations"
    ensure_no_symlink_components(root, generations)
    generations.mkdir(parents=True, exist_ok=True)
    generation = generations / uuid4().hex
    generation.mkdir()
    return generation


def publish_current(paths: ProjectPaths, model: str, groups: dict[int, str]) -> None:
    root = _result_root(paths, model)
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / f".current-{uuid4().hex}.json"
    try:
        temporary.write_text(
            json.dumps(
                {
                    "version": 1,
                    "groups": {
                        str(key): value for key, value in sorted(groups.items())
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(root / "current.json")
    finally:
        temporary.unlink(missing_ok=True)


def cleanup_generations(
    paths: ProjectPaths, model: str, current: dict[int, str]
) -> None:
    root = _result_root(paths, model)
    generations = root / "generations"
    if not generations.exists():
        return
    ensure_no_symlink_components(root, generations)
    keep = {root / value for value in current.values()}
    for generation in generations.iterdir():
        if (
            generation.is_symlink()
            or not generation.is_dir()
            or not _RUN_ID.fullmatch(generation.name)
        ):
            raise ValueError(f"invalid result generation entry: {generation}")
        for group in generation.iterdir():
            if (
                group.is_symlink()
                or not group.is_dir()
                or not re.fullmatch(r"group_\d+", group.name)
            ):
                raise ValueError(f"invalid result group entry: {group}")
            if group not in keep:
                shutil.rmtree(group)
        if not any(generation.iterdir()):
            generation.rmdir()
