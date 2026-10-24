from __future__ import annotations

import json
from pathlib import Path

import pytest
from group_evaluation_helpers import (
    FakePredictor,
    aligned,
    make_model_artifacts,
    project,
    recorder,
)

from app.common.config import load_config
from app.common.paths import ProjectPaths
from app.image_preparation.preparation import prepare_testing
from app.model_evaluation import cli as evaluation_cli


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


def test_result_group_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _, paths = project(tmp_path)
    config_file = paths.model_config("XX")
    payload = json.loads(config_file.read_text())
    for group_id in (9, 10, 100):
        group = dict(payload["groups"][0])
        group["id"] = group_id
        payload["groups"].append(group)
        payload["group_detail"][str(group_id)] = json.loads(
            json.dumps(payload["group_detail"]["0"])
        )
    config_file.write_text(json.dumps(payload))
    config = load_config(tmp_path, "XX")
    prepare_testing(config, paths, aligner=aligned)
    for group_id in (9, 10, 100):
        make_model_artifacts(config, paths, group_id)
    monkeypatch.setattr(
        evaluation_cli,
        "_run",
        lambda _cmd, _model, action, **_kw: action(paths, recorder()),
    )
    monkeypatch.setattr(evaluation_cli, "CheckpointPredictor", FakePredictor)
    evaluation_cli._test_command(model="XX", group=None)
    assert str(paths.results("XX")) in capsys.readouterr().err
    for group_id, name in (
        (0, "group_00"),
        (9, "group_09"),
        (10, "group_10"),
        (100, "group_100"),
    ):
        result_dir = paths.result_group("XX", group_id)
        assert result_dir == tmp_path / "data/06_result/XX" / name
        assert sorted(path.name for path in result_dir.iterdir()) == [
            "sample.png.json",
            "sample_00.png_result.png",
            "sample_01.png_result.png",
        ]
        assert (
            json.loads((result_dir / "sample.png.json").read_text())["group"]
            == group_id
        )
