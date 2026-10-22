from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.common.paths import ProjectPaths
from app.common.result_index import publish_current, read_current


@pytest.mark.parametrize(
    ("group", "name"),
    [(0, "group_00"), (9, "group_09"), (10, "group_10"), (100, "group_100")],
)
def test_preparation_group_names(tmp_path: Path, group: int, name: str) -> None:
    paths = ProjectPaths(tmp_path)
    assert paths.check_image("XX", group).name == f"{name}.png"
    assert paths.prepared_train("XX", group).name == name
    assert paths.group_name(group) == name


@pytest.mark.parametrize(
    ("group", "name"),
    [(0, "group_00"), (9, "group_09"), (10, "group_10"), (100, "group_100")],
)
def test_training_group_names(tmp_path: Path, group: int, name: str) -> None:
    paths = ProjectPaths(tmp_path)
    assert paths.study_dir("XX", group).name == name
    assert paths.checkpoint("XX", group).name == f"{name}.ckpt"


def test_result_group_names(tmp_path: Path) -> None:
    paths = ProjectPaths(tmp_path)
    generation = "a" * 32
    expected: dict[int, str] = {}
    for group in (0, 9, 10, 100):
        relative = f"generations/{generation}/{paths.group_name(group)}"
        (paths.results("XX") / relative).mkdir(parents=True)
        expected[group] = relative
    publish_current(paths, "XX", expected)
    assert read_current(paths, "XX", allowed_group_ids=set(expected)) == expected
    payload = json.loads(paths.result_current("XX").read_text())
    assert set(payload["groups"]) == {"0", "9", "10", "100"}
