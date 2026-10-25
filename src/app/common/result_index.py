"""Safe staging and publication of group inspection results."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from uuid import uuid4

from app.common.atomic import publish_staged_directory
from app.common.paths import ProjectPaths, ensure_no_symlink_components

_RUN_ID = r"[0-9a-f]{32}"
_GROUP = r"group_(?:0[0-9]|[1-9][0-9]+)"
_STAGE = re.compile(rf"\.stage-{_RUN_ID}")
_GROUP_NAME = re.compile(_GROUP)
_SOURCE_JSON = re.compile(r".+\.(?:png|jpg|jpeg|bmp|tif|tiff)\.json", re.I)
_RESULT_IMAGE = re.compile(r".+_result\.png", re.I)


def _root(paths: ProjectPaths, model: str) -> Path:
    root = paths.results(model)
    ensure_no_symlink_components(paths.root, root)
    return root


def _validate_group(directory: Path, *, allow_temporary: bool = False) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError(f"invalid result group directory: {directory}")
    for entry in directory.iterdir():
        valid_file = bool(
            _SOURCE_JSON.fullmatch(entry.name)
            or _RESULT_IMAGE.fullmatch(entry.name)
            or (allow_temporary and entry.name.endswith(".json.tmp"))
        )
        if entry.is_symlink() or not entry.is_file() or not valid_file:
            raise ValueError(f"unmanaged result group entry: {entry}")


def _validate_stage(stage: Path) -> None:
    if stage.is_symlink() or not stage.is_dir():
        raise ValueError(f"invalid result temporary area: {stage}")
    for group in stage.iterdir():
        if not _GROUP_NAME.fullmatch(group.name):
            raise ValueError(f"unmanaged result temporary entry: {group}")
        _validate_group(group, allow_temporary=True)


def create_result_stage(paths: ProjectPaths, model: str) -> Path:
    """Clear app-owned incomplete stages before a run."""

    root = _root(paths, model)
    root.mkdir(parents=True, exist_ok=True)
    for stale in root.iterdir():
        if _STAGE.fullmatch(stale.name):
            _validate_stage(stale)
            shutil.rmtree(stale)
    stage = root / f".stage-{uuid4().hex}"
    stage.mkdir()
    return stage


def validate_publish_targets(
    paths: ProjectPaths,
    model: str,
    *,
    selected_ids: set[int],
    configured_ids: set[int] | None = None,
) -> None:
    """Reject unsafe managed targets before any group publication starts."""

    root = _root(paths, model)
    for group in selected_ids:
        target = paths.result_group(model, group)
        if target.exists() or target.is_symlink():
            _validate_group(target)
    if configured_ids is not None and root.exists():
        keep = {paths.group_name(group) for group in configured_ids}
        for entry in root.iterdir():
            if _GROUP_NAME.fullmatch(entry.name) and entry.name not in keep:
                _validate_group(entry)


def publish_group(paths: ProjectPaths, model: str, group: int, stage: Path) -> None:
    target = paths.result_group(model, group)
    staged_group = stage / paths.group_name(group)
    _validate_group(staged_group)
    if target.exists() or target.is_symlink():
        _validate_group(target)
    publish_staged_directory(staged_group, target)


def remove_result_stage(stage: Path) -> None:
    if stage.exists() or stage.is_symlink():
        _validate_stage(stage)
        shutil.rmtree(stage)


def remove_unconfigured_groups(
    paths: ProjectPaths, model: str, *, configured_ids: set[int]
) -> None:
    """Remove only canonical group directories omitted from a full run."""

    root = _root(paths, model)
    keep = {paths.group_name(group) for group in configured_ids}
    for entry in root.iterdir():
        if _GROUP_NAME.fullmatch(entry.name) and entry.name not in keep:
            _validate_group(entry)
            shutil.rmtree(entry)
