from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import typer
from conftest import write_test_image
from group_evaluation_helpers import FakePredictor, aligned, project, recorder

from app.common.config import load_config, preparation_fingerprint
from app.common.contracts import PreparationManifest
from app.common.image_io import ImageReadError
from app.image_preparation import cli as preparation_cli
from app.image_preparation.imaging import AlignmentError
from app.image_preparation.preparation import (
    PreparationError,
    prepare_testing,
    prepare_training,
)
from app.model_evaluation import cli as evaluation_cli


def _two(tmp_path: Path):
    config, paths = project(tmp_path, two=True)
    return config, paths


def _evaluate(monkeypatch: pytest.MonkeyPatch, paths, group: int | None):
    run = recorder()
    monkeypatch.setattr(
        evaluation_cli,
        "_run",
        lambda _command, _model, action, **_kw: action(paths, run),
    )
    monkeypatch.setattr(
        evaluation_cli,
        "CheckpointPredictor",
        lambda *_args, **_kwargs: FakePredictor(score=0.5),
    )
    evaluation_cli._test_command(model="XX", group=group)
    return run


def test_group_prepare_isolated(tmp_path: Path) -> None:
    config, paths = _two(tmp_path)
    untouched = paths.prepared_test("XX", 0)
    untouched.mkdir(parents=True, exist_ok=True)
    (untouched / "old.txt").write_text("old")
    manifests = prepare_testing(config, paths, group=1, aligner=aligned)
    assert list(manifests) == [1]
    assert {
        split.split_id for source in manifests[1].sources for split in source.splits
    } == {0}
    assert (untouched / "old.txt").read_text() == "old"
    assert (paths.prepared_test("XX", 1) / "sample_00.png").is_file()
    assert not (paths.prepared_test("XX", 1) / "sample_01.png").exists()


def test_group_alignment_failure(tmp_path: Path) -> None:
    config, paths = _two(tmp_path)

    def fail(*_args):
        raise AlignmentError("few matches")

    source = prepare_testing(config, paths, group=1, aligner=fail)[1].sources[0]
    assert source.alignment.status == "undetermined"
    assert source.alignment.reason == "few matches"
    assert source.alignment.recapture_required
    assert not source.splits


def test_group_crop_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config, paths = _two(tmp_path)
    target = paths.prepared_test("XX", 1)
    target.mkdir(parents=True, exist_ok=True)
    (target / "old.txt").write_text("old")
    payload = json.loads(paths.model_config("XX").read_text())
    payload["range"][0]["x"] = 30
    paths.model_config("XX").write_text(json.dumps(payload))
    config = load_config(tmp_path, "XX")
    with pytest.raises(PreparationError, match="sample.png.*0"):
        prepare_testing(config, paths, group=1, aligner=aligned)
    assert (target / "old.txt").read_text() == "old"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        preparation_cli,
        "prepare_testing",
        lambda config, project_paths, **kwargs: prepare_testing(
            config, project_paths, aligner=aligned, **kwargs
        ),
    )
    capsys.readouterr()
    with pytest.raises(typer.Exit) as error:
        preparation_cli._test_pre_command(model="XX", group=1)
    captured = capsys.readouterr()
    assert error.value.exit_code == 3
    assert "group 1" in captured.err
    assert "sample.png" in captured.err
    message = json.loads(captured.out)["errors"][0]
    assert "group 1" in message
    assert re.search(r"sample\.png.*0", message)
    assert (target / "old.txt").read_text() == "old"


def test_group_read_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config, paths = _two(tmp_path)
    prepare_testing(config, paths, group=1, aligner=aligned)
    target = paths.prepared_test("XX", 1)
    before = (target / "manifest.json").read_bytes()
    (paths.original_test("XX") / "sample.png").write_bytes(b"bad")
    with pytest.raises(ImageReadError, match="sample.png"):
        prepare_testing(config, paths, group=1, aligner=aligned)
    assert (target / "manifest.json").read_bytes() == before
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        preparation_cli,
        "prepare_testing",
        lambda config, project_paths, **kwargs: prepare_testing(
            config, project_paths, aligner=aligned, **kwargs
        ),
    )
    capsys.readouterr()
    with pytest.raises(typer.Exit) as error:
        preparation_cli._test_pre_command(model="XX", group=1)
    captured = capsys.readouterr()
    assert error.value.exit_code == 3
    assert "group 1" in captured.err
    assert "sample.png" in captured.err
    assert "group 1" in json.loads(captured.out)["errors"][0]
    assert (target / "manifest.json").read_bytes() == before


def test_group_stale_stage(tmp_path: Path) -> None:
    config, paths = _two(tmp_path)
    target = paths.prepared_test("XX", 1)
    target.mkdir(parents=True, exist_ok=True)
    (target / "old.txt").write_text("old")
    stage = target.with_name(f".{target.name}-stage-{'a' * 32}")
    stage.mkdir()
    prepare_testing(config, paths, group=1, aligner=aligned)
    assert not stage.exists()
    assert not (target / "old.txt").exists()


def test_all_groups_prepare(tmp_path: Path) -> None:
    config, paths = _two(tmp_path)
    calls: list[str] = []

    def counting(image, reference, settings):
        calls.append("align")
        return aligned(image, reference, settings)

    manifests = prepare_testing(config, paths, aligner=counting)
    assert list(manifests) == [0, 1]
    assert len(calls) == 1
    assert {split.split_id for split in manifests[0].sources[0].splits} == {0, 1}
    assert {split.split_id for split in manifests[1].sources[0].splits} == {0}


def test_unknown_group(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = _two(tmp_path)
    before = (paths.prepared_test("XX", 0) / "manifest.json").read_bytes()
    monkeypatch.chdir(tmp_path)
    with pytest.raises(typer.Exit) as error:
        preparation_cli._test_pre_command(model="XX", group=9)
    assert error.value.exit_code == 2
    assert (paths.prepared_test("XX", 0) / "manifest.json").read_bytes() == before


def test_cli_group_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, paths = _two(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        preparation_cli,
        "prepare_testing",
        lambda config, project_paths, **kwargs: prepare_testing(
            config, project_paths, aligner=aligned, **kwargs
        ),
    )
    capsys.readouterr()
    preparation_cli._test_pre_command(model="XX", group=1)
    record = json.loads(capsys.readouterr().out)
    assert record["groups"] == [1]
    assert record["exit_code"] == 0
    assert (paths.prepared_test("XX", 1) / "manifest.json").is_file()


def test_training_manifest_unchanged(tmp_path: Path) -> None:
    config, paths = _two(tmp_path)
    for name in ("base.png", "a.png"):
        write_test_image(paths.original_train("XX") / name, size=32)
    manifest = prepare_training(config, paths, group=1, aligner=aligned)[1]
    assert manifest.group == 1
    assert manifest.range_ids == [0]
    assert manifest.preparation_fingerprint == preparation_fingerprint(
        config, group=config.part.select_groups(1)[0]
    )


def test_testing_group_fingerprint(tmp_path: Path) -> None:
    config, paths = _two(tmp_path)
    manifest = prepare_testing(config, paths, group=1, aligner=aligned)[1]
    group = config.part.select_groups(1)[0]
    assert manifest.group == 1 and manifest.range_ids == [0]
    assert manifest.preparation_fingerprint == preparation_fingerprint(
        config, group=group, testing=True
    )
    payload = json.loads(paths.model_config("XX").read_text())
    payload["blacklist"] = [{"image": "a.png", "id": [0]}]
    payload["groups"][1]["ranges"][0]["inspection_threshold"] = 0.8
    paths.model_config("XX").write_text(json.dumps(payload))
    changed = load_config(tmp_path, "XX")
    assert manifest.preparation_fingerprint == preparation_fingerprint(
        changed, group=changed.part.select_groups(1)[0], testing=True
    )


def test_brightness_fingerprint(tmp_path: Path) -> None:
    config, paths = _two(tmp_path)
    before = preparation_fingerprint(
        config, group=config.part.select_groups(1)[0], testing=True
    )
    payload = json.loads(paths.model_config("XX").read_text())
    payload["brightness_normalization"] = {"enabled": True}
    paths.model_config("XX").write_text(json.dumps(payload))
    changed = load_config(tmp_path, "XX")
    assert before != preparation_fingerprint(
        changed, group=changed.part.select_groups(1)[0], testing=True
    )


def test_inspection_value_fingerprint(tmp_path: Path) -> None:
    config, paths = _two(tmp_path)
    before = preparation_fingerprint(
        config, group=config.part.select_groups(1)[0], testing=True
    )
    payload = json.loads(paths.model_config("XX").read_text())
    payload["groups"][1]["ranges"][0]["heatmap_range"] = {"min": 0, "max": 4}
    paths.model_config("XX").write_text(json.dumps(payload))
    changed = load_config(tmp_path, "XX")
    assert before == preparation_fingerprint(
        changed, group=changed.part.select_groups(1)[0], testing=True
    )


def test_single_evaluation_uses_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = _two(tmp_path)
    (paths.prepared_test("XX", 0) / "manifest.json").unlink()
    _evaluate(monkeypatch, paths, 1)
    assert (paths.result_group("XX", 1) / "sample.png.json").is_file()
    assert not paths.result_group("XX", 0).exists()


def test_all_evaluation_uses_groups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = _two(tmp_path)
    _evaluate(monkeypatch, paths, None)
    assert (paths.result_group("XX", 0) / "sample.png.json").is_file()
    assert (paths.result_group("XX", 1) / "sample.png.json").is_file()


@pytest.mark.parametrize("broken", ["missing", "fingerprint"])
def test_evaluation_rejects_bad_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    _, paths = _two(tmp_path)
    _evaluate(monkeypatch, paths, None)
    before = {
        group: (paths.result_group("XX", group) / "sample.png.json").read_bytes()
        for group in (0, 1)
    }
    target = paths.prepared_test("XX", 1) / "manifest.json"
    if broken == "missing":
        target.unlink()
    else:
        manifest = PreparationManifest.read_json(target)
        manifest.preparation_fingerprint = "0" * 64
        manifest.write_json(target)
    with pytest.raises(
        ValueError,
        match=f"group 1.*{'is missing' if broken == 'missing' else 'fingerprint mismatch'}",
    ) as error:
        _evaluate(monkeypatch, paths, None)
    assert "rerun train-pre or test-pre" in str(error.value)
    assert {
        group: (paths.result_group("XX", group) / "sample.png.json").read_bytes()
        for group in (0, 1)
    } == before
