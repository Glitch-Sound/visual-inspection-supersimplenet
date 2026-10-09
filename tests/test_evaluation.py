from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import torch
import typer
from group_evaluation_helpers import FakePredictor, project, recorder
from typer.testing import CliRunner

from app.common.config import load_config
from app.common.result_index import (
    create_generation,
    read_current,
)
from app.model_evaluation import cli as evaluation_cli
from app.model_evaluation import evaluation
from app.model_evaluation.cli import _test_command
from app.model_evaluation.evaluation import (
    _heatmap,
    effective_threshold,
    require_heatmap_range,
    validate_score_contract,
)
from app.model_evaluation.predictor import load_checkpoint_metadata


def _run(
    monkeypatch: pytest.MonkeyPatch,
    paths,
    *,
    group=None,
    score=0.5,
    predictor_factory=None,
):
    run = recorder()
    monkeypatch.setattr(
        evaluation_cli, "_run", lambda _cmd, _model, action, **_kw: action(paths, run)
    )
    monkeypatch.setattr(
        evaluation_cli,
        "CheckpointPredictor",
        predictor_factory or (lambda *_a, **_kw: FakePredictor(score=score)),
    )
    return _test_command(model="XX", group=group), run


def _current(paths) -> dict[int, str]:
    return read_current(paths, "XX", allowed_group_ids={0, 1})


def test_group_req_023_s01(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths)
    assert set(_current(paths)) == {0, 1}


def test_group_req_023_s02(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths, group=1)
    assert set(_current(paths)) == {1}


def test_group_req_023_s04(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path)
    with pytest.raises(ValueError, match="available groups"):
        _run(monkeypatch, paths, group=9)


def test_group_req_023_s03(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths)
    before = _current(paths)
    old_result = paths.results("XX") / before[1] / "sample.png.json"
    old_contents = old_result.read_bytes()
    paths.checkpoint("XX", 1).unlink()
    with pytest.raises(ValueError, match="group 1"):
        _run(
            monkeypatch,
            paths,
            predictor_factory=lambda *_a, **_kw: pytest.fail("predictor started"),
        )
    assert _current(paths) == before
    assert old_result.read_bytes() == old_contents


@pytest.mark.parametrize("failure", ["evaluation", "result_image_write"])
def test_group_req_023_s05(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths)
    before = _current(paths)
    old_result = paths.results("XX") / before[1] / "sample.png.json"
    old_contents = old_result.read_bytes()
    if failure == "evaluation":
        original = evaluation_cli.evaluate_model

        def fail_second(config, group, *args, **kwargs):
            if group.id == 1:
                raise RuntimeError("injected failure")
            return original(config, group, *args, **kwargs)

        monkeypatch.setattr(evaluation_cli, "evaluate_model", fail_second)
    else:
        original_write = evaluation.write_image

        def fail_image_write(path, image):
            if path.parent.name == "group_1":
                raise OSError("injected image write failure")
            return original_write(path, image)

        monkeypatch.setattr(evaluation, "write_image", fail_image_write)
    with pytest.raises(RuntimeError, match="group 1 failed"):
        _run(monkeypatch, paths)
    assert _current(paths) == before
    assert old_result.read_bytes() == old_contents


def test_group_req_010_s01(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths)
    current = _current(paths)
    first = paths.results("XX") / current[0] / "sample.png.json"
    second = paths.results("XX") / current[1] / "sample.png.json"
    assert {item["split_id"] for item in json.loads(first.read_text())["splits"]} == {
        0,
        1,
    }
    assert {item["split_id"] for item in json.loads(second.read_text())["splits"]} == {
        0
    }


def test_group_req_010_s02(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths, group=1)
    assert set(_current(paths)) == {1}


def test_group_req_010_s03(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths)
    before = _current(paths)
    _run(monkeypatch, paths, group=1)
    after = _current(paths)
    assert before[0] == after[0]
    assert before[1] != after[1]


def test_group_req_010_s04(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path, two=True)
    paths.study_dir("XX", 0).joinpath("best_trial.json").unlink()
    with pytest.raises(ValueError, match="group 0"):
        _run(monkeypatch, paths)


def test_group_req_013_s01(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths)
    before = _current(paths)
    _run(monkeypatch, paths)
    after = _current(paths)
    assert all(before[key] != after[key] for key in before)
    assert all((paths.results("XX") / value).is_dir() for value in after.values())


def test_group_req_013_s02(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths)
    before = _current(paths)
    _run(monkeypatch, paths, group=0)
    after = _current(paths)
    assert before[1] == after[1]
    assert before[0] != after[0]


def test_group_req_013_s03(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path)
    _run(monkeypatch, paths)
    before = _current(paths)
    monkeypatch.setattr(
        evaluation_cli,
        "publish_current",
        lambda *_args: (_ for _ in ()).throw(OSError("interrupted")),
    )
    with pytest.raises(OSError):
        _run(monkeypatch, paths)
    assert _current(paths) == before


def test_group_req_013_s04(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path)
    _run(monkeypatch, paths)
    before = _current(paths)
    monkeypatch.setattr(
        evaluation_cli,
        "cleanup_generations",
        lambda *_args: (_ for _ in ()).throw(OSError("interrupted")),
    )
    _, run = _run(monkeypatch, paths)
    assert _current(paths) != before
    assert any("cleanup deferred" in item for item in run.warnings)


@pytest.mark.parametrize("bad", ["version", "path", "missing", "symlink", "group"])
def test_group_req_013_s05(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths)
    current = paths.result_current("XX")
    payload = json.loads(current.read_text())
    if bad == "version":
        payload["version"] = 2
    elif bad == "path":
        payload["groups"]["0"] = "../outside"
    elif bad == "missing":
        payload["groups"]["0"] = "generations/" + "0" * 32 + "/group_0"
    elif bad == "group":
        payload["groups"]["9"] = payload["groups"].pop("0")
    else:
        current.unlink()
        outside = tmp_path / "outside.json"
        outside.write_text("outside")
        current.symlink_to(outside)
    if bad != "symlink":
        current.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        read_current(paths, "XX", allowed_group_ids={0, 1})
    with pytest.raises(ValueError):
        _run(monkeypatch, paths, group=0)


def test_group_req_013_s06() -> None:
    app = typer.Typer()
    app.command()(_test_command)
    result = CliRunner().invoke(app, ["--model", "XX", "--restart"])
    assert result.exit_code != 0
    assert "restart" in result.output


def test_group_req_013_s07(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path, two=True)
    current = paths.result_current("XX")
    current.parent.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text("safe")
    current.symlink_to(outside)
    _run(monkeypatch, paths)
    assert not current.is_symlink()
    assert outside.read_text() == "safe"
    assert set(_current(paths)) == {0, 1}


def test_group_req_013_s08(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path)
    current = paths.result_current("XX")
    current.parent.mkdir(parents=True)
    current.write_text("invalid")
    monkeypatch.chdir(tmp_path)
    from app.common.cli import _run as execute

    execute("check", "XX", lambda _paths, _recorder: "ok")
    assert current.read_text() == "invalid"


def test_group_req_013_s09(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths)
    before = _current(paths)
    _run(monkeypatch, paths, group=0)
    after = _current(paths)
    assert not (paths.results("XX") / before[0]).exists()
    assert (paths.results("XX") / before[1]).exists()
    assert sorted(
        path.name for path in paths.result_generations("XX").iterdir()
    ) == sorted({Path(value).parts[1] for value in after.values()})


def test_group_req_013_s10(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path)
    _run(monkeypatch, paths)
    orphan = create_generation(paths, "XX") / "group_0"
    orphan.mkdir()
    monkeypatch.chdir(tmp_path)
    from app.common.cli import _run as execute

    execute("check", "XX", lambda _paths, _recorder: "ok")
    assert not orphan.exists()


def test_group_req_016_s01(tmp_path: Path) -> None:
    config, paths = project(tmp_path)
    group = config.part.groups[0]
    metadata = load_checkpoint_metadata(paths.checkpoint("XX", 0))
    assert validate_score_contract(config, group, metadata) == 0.4


def test_group_req_016_s02(tmp_path: Path) -> None:
    _, paths = project(tmp_path)
    torch.save({"state_dict": {}}, paths.checkpoint("XX", 0))
    with pytest.raises(ValueError, match="metadata"):
        load_checkpoint_metadata(paths.checkpoint("XX", 0))


def test_group_req_016_s03(tmp_path: Path) -> None:
    config, paths = project(tmp_path)
    metadata = load_checkpoint_metadata(paths.checkpoint("XX", 0))
    metadata["group"] = 1
    with pytest.raises(ValueError, match="group mismatch"):
        validate_score_contract(config, config.part.groups[0], metadata)


def test_group_req_018_s01(tmp_path: Path) -> None:
    config, _ = project(tmp_path)
    group = config.part.groups[0]
    assert effective_threshold(group, 0.4) == 0.4


def test_group_req_018_s02(tmp_path: Path) -> None:
    config, _ = project(tmp_path)
    assert config.part.groups[0].inspection_threshold is None
    assert effective_threshold(config.part.groups[0], 0.4) == 0.4


def test_group_req_018_s03(tmp_path: Path) -> None:
    config, _ = project(tmp_path)
    group = config.part.groups[0]
    group.inspection_threshold = 0.7
    assert effective_threshold(group, 0.4) == 0.7
    assert group.optuna_settings.threshold.value == 0.4


@pytest.mark.parametrize("value", [0.0, 1.0])
def test_group_req_018_s04(tmp_path: Path, value: float) -> None:
    config, _ = project(tmp_path)
    group = config.part.groups[0]
    group.inspection_threshold = value
    assert effective_threshold(group, 0.4) == value


@pytest.mark.parametrize("value", [-0.1, 1.1, "bad", True])
def test_group_req_018_s05(tmp_path: Path, value: object) -> None:
    _, paths = project(tmp_path)
    payload = json.loads(paths.model_config("XX").read_text())
    payload["groups"][0]["inspection_threshold"] = value
    paths.model_config("XX").write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="inspection_threshold"):
        load_config(tmp_path, "XX")


def test_group_req_018_s06(tmp_path: Path) -> None:
    config, paths = project(tmp_path)
    group = config.part.groups[0]
    group.optuna_settings.threshold.value = 0.6
    metadata = load_checkpoint_metadata(paths.checkpoint("XX", 0))
    with pytest.raises(ValueError, match="threshold"):
        validate_score_contract(config, group, metadata)


def test_group_req_019_s01(tmp_path: Path) -> None:
    config, _ = project(tmp_path)
    group = config.part.groups[0]
    image = np.zeros((8, 8, 3), dtype=np.uint8)
    heatmap = _heatmap(
        image, np.ones((8, 8), dtype=np.float32), require_heatmap_range(group)
    )
    assert heatmap.shape == image.shape
    assert heatmap.any()


@pytest.mark.parametrize("value", [None, {"min": 1, "max": 1}, {"min": True, "max": 2}])
def test_group_req_019_s02(tmp_path: Path, value: object) -> None:
    _, paths = project(tmp_path)
    payload = json.loads(paths.model_config("XX").read_text())
    payload["groups"][0]["heatmap_range"] = value
    paths.model_config("XX").write_text(json.dumps(payload))
    if value is None:
        with pytest.raises(ValueError, match="heatmap_range"):
            require_heatmap_range(load_config(tmp_path, "XX").part.groups[0])
    else:
        with pytest.raises(ValueError, match="heatmap_range"):
            load_config(tmp_path, "XX")
