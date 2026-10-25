from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path

import pytest
import typer
from conftest import build_project, write_test_image
from pydantic import ValidationError

from app.common import cli as common_cli
from app.common import contracts
from app.common.config import (
    load_config,
    load_model_config,
    preparation_fingerprint,
    write_threshold,
)
from app.common.runtime import DeviceSelection
from app.image_preparation.cli import (
    _check_command,
    _test_pre_command,
    _train_pre_command,
)
from app.image_preparation.imaging import AlignedImage
from app.image_preparation.preparation import prepare_testing, prepare_training
from app.model_evaluation.cli import _test_command
from app.model_training.cli import _train_command


def _payload(root: Path) -> tuple[Path, dict]:
    path = root / "config" / "part_XX.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _assert_invalid_training_preserves_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from app.common.paths import ProjectPaths

    paths = ProjectPaths(tmp_path)
    checkpoint = paths.checkpoint("XX", 0)
    study = paths.study_dir("XX", 0) / "study.db"
    for artifact in (checkpoint, study):
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(b"previous artifact")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        common_cli,
        "select_device",
        lambda: DeviceSelection("cpu", "test", "test"),
    )
    with pytest.raises(typer.Exit) as error:
        _train_command(model="XX", group=0)
    assert error.value.exit_code == 2
    output = capsys.readouterr()
    assert "入力不備" in output.err
    assert json.loads(output.out)["exit_code"] == 2
    assert checkpoint.read_bytes() == study.read_bytes() == b"previous artifact"


def test_synthetic_anomaly_defaults(tmp_path: Path) -> None:
    build_project(tmp_path)
    path, payload = _payload(tmp_path)
    first = load_model_config(path).groups[0].synthetic_anomaly
    assert first.noise_std.model_dump() == {"min": 0.010, "max": 0.020}
    assert first.perlin_threshold.model_dump() == {"min": 0.2, "max": 0.4}
    assert first.perlin_scale_exponent.model_dump() == {"min": 0, "max": 5}

    payload["group_detail"]["0"]["synthetic_anomaly"] = {
        "noise_std": {"min": 0.03, "max": 0.03}
    }
    _save(path, payload)
    partial = load_model_config(path).groups[0].synthetic_anomaly
    assert partial.noise_std.min == partial.noise_std.max == 0.03
    assert partial.perlin_threshold.model_dump() == first.perlin_threshold.model_dump()
    assert (
        partial.perlin_scale_exponent.model_dump()
        == first.perlin_scale_exponent.model_dump()
    )


@pytest.mark.parametrize(
    ("name", "bounds"),
    [
        ("noise_std", {"min": 0, "max": 0.02}),
        ("noise_std", {"min": 0.03, "max": 0.02}),
        ("noise_std", {"min": float("inf"), "max": 0.02}),
        ("perlin_threshold", {"min": -0.1, "max": 0.4}),
        ("perlin_threshold", {"min": 0.2, "max": 1}),
        ("perlin_threshold", {"min": 0.5, "max": 0.4}),
        ("perlin_scale_exponent", {"min": -1, "max": 5}),
        ("perlin_scale_exponent", {"min": 0, "max": 6}),
        ("perlin_scale_exponent", {"min": 4, "max": 3}),
    ],
)
def test_synthetic_anomaly_rejects_invalid_bounds(
    tmp_path: Path,
    name: str,
    bounds: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    build_project(tmp_path)
    path, payload = _payload(tmp_path)
    payload["group_detail"]["0"]["synthetic_anomaly"] = {name: bounds}
    _save(path, payload)
    before = path.read_bytes()
    with pytest.raises(ValidationError, match=name):
        load_model_config(path)
    _assert_invalid_training_preserves_artifacts(tmp_path, monkeypatch, capsys)
    assert path.read_bytes() == before
    payload["group_detail"]["0"]["synthetic_anomaly"][name] = (
        {
            "min": 0.2,
            "max": 0.2,
        }
        if name == "perlin_threshold"
        else (
            {"min": 1, "max": 1}
            if name == "perlin_scale_exponent"
            else {"min": 0.02, "max": 0.02}
        )
    )
    _save(path, payload)
    assert load_model_config(path).groups[0].synthetic_anomaly is not None


@pytest.mark.parametrize(
    ("name", "bounds"),
    [
        ("noise_std", {"min": True, "max": 0.02}),
        ("perlin_threshold", {"min": "0.2", "max": 0.4}),
        ("perlin_scale_exponent", {"min": 0.2, "max": 5}),
        ("perlin_scale_exponent", {"min": False, "max": 5}),
    ],
)
def test_synthetic_anomaly_rejects_invalid_types(
    tmp_path: Path,
    name: str,
    bounds: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    build_project(tmp_path)
    path, payload = _payload(tmp_path)
    payload["group_detail"]["0"]["synthetic_anomaly"] = {name: bounds}
    _save(path, payload)
    with pytest.raises(ValidationError, match=name):
        load_model_config(path)
    _assert_invalid_training_preserves_artifacts(tmp_path, monkeypatch, capsys)


def test_group_req_021_s01(tmp_path: Path) -> None:
    config, _ = build_project(
        tmp_path, ranges=[{"id": 0, "x": 0, "y": 0}, {"id": 1, "x": 8, "y": 0}]
    )
    path, payload = _payload(tmp_path)
    second = json.loads(json.dumps(payload["groups"][0]))
    second["id"] = 1
    second["ranges"] = [second["ranges"][0]]
    payload["groups"].append(second)
    payload["group_detail"]["1"] = json.loads(json.dumps(payload["group_detail"]["0"]))
    payload["group_detail"]["1"]["optuna_settings"]["execution"]["seed"] = 73
    _save(path, payload)
    loaded = load_config(tmp_path, "XX")
    assert [group.id for group in loaded.part.select_groups()] == [0, 1]
    assert [item.id for item in loaded.part.ranges_for(loaded.part.groups[1])] == [0]
    assert loaded.part.groups[1].optuna_settings.execution.seed == 73
    assert loaded.part.groups[0].optuna_settings.execution.seed == 42
    assert config.part.groups[0].range_ids == [0, 1]


def test_per_range_shared_id_between_groups(tmp_path: Path) -> None:
    build_project(tmp_path)
    path, payload = _payload(tmp_path)
    second = json.loads(json.dumps(payload["groups"][0]))
    second["id"] = 1
    second["ranges"][0]["inspection_threshold"] = 0.7
    second["ranges"][0]["heatmap_range"] = {"min": -1.0, "max": 2.0}
    payload["groups"].append(second)
    payload["group_detail"]["1"] = json.loads(json.dumps(payload["group_detail"]["0"]))
    _save(path, payload)
    groups = load_config(tmp_path, "XX").part.select_groups()
    assert [group.range_ids for group in groups] == [[0], [0]]
    assert groups[0].ranges[0].inspection_threshold is None
    assert groups[1].ranges[0].inspection_threshold == 0.7
    assert groups[1].ranges[0].heatmap_range.model_dump() == {
        "min": -1.0,
        "max": 2.0,
    }


@pytest.mark.parametrize(
    "command",
    [
        _check_command,
        _train_pre_command,
        _train_command,
        _test_pre_command,
        _test_command,
    ],
)
@pytest.mark.parametrize(
    "mutation",
    [
        "missing_ranges",
        "empty_ranges",
        "missing_id",
        "duplicate_id",
        "unknown_id",
        "missing_threshold",
        "missing_heatmap",
        "invalid_bounds",
        "invalid_threshold",
        "invalid_heatmap_type",
        "old_range_ids",
        "old_threshold",
        "old_heatmap",
    ],
)
def test_per_range_invalid_config_all_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command,
    mutation: str,
) -> None:
    build_project(tmp_path)
    path, payload = _payload(tmp_path)
    group = payload["groups"][0]
    entry = group["ranges"][0]
    if mutation == "missing_ranges":
        group.pop("ranges")
    elif mutation == "empty_ranges":
        group["ranges"] = []
    elif mutation == "missing_id":
        entry.pop("id")
    elif mutation == "duplicate_id":
        group["ranges"].append(json.loads(json.dumps(entry)))
    elif mutation == "unknown_id":
        entry["id"] = 3
    elif mutation == "missing_threshold":
        entry.pop("inspection_threshold")
    elif mutation == "missing_heatmap":
        entry.pop("heatmap_range")
    elif mutation == "invalid_bounds":
        entry["heatmap_range"] = {"min": 1.0, "max": 1.0}
    elif mutation == "invalid_threshold":
        entry["inspection_threshold"] = True
    elif mutation == "invalid_heatmap_type":
        entry["heatmap_range"] = {"min": True, "max": 1.0}
    elif mutation == "old_range_ids":
        group["range_ids"] = [0]
    elif mutation == "old_threshold":
        group["inspection_threshold"] = 0.5
    else:
        group["heatmap_range"] = {"min": 0.0, "max": 1.0}
    _save(path, payload)
    marker = tmp_path / "data" / "06_result" / "XX" / "group_00" / "old.json"
    marker.parent.mkdir(parents=True)
    marker.write_text("old", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        common_cli, "select_device", lambda: DeviceSelection("cpu", "test", "test")
    )
    with pytest.raises(typer.Exit) as error:
        if command in (_train_pre_command, _train_command, _test_command):
            command(model="XX", group=0)
        else:
            command(model="XX")
    output = capsys.readouterr()
    assert error.value.exit_code == 2
    assert "group 0" in output.err
    if mutation == "duplicate_id":
        assert "range 0 is duplicated" in output.err
    assert any(name in output.err for name in ("range", "threshold", "heatmap"))
    assert json.loads(output.out)["exit_code"] == 2
    assert marker.read_text(encoding="utf-8") == "old"


@pytest.mark.parametrize(
    "field", ["range_ids", "inspection_threshold", "heatmap_range"]
)
def test_per_range_rejects_group_legacy_fields(tmp_path: Path, field: str) -> None:
    build_project(tmp_path)
    path, payload = _payload(tmp_path)
    payload["groups"][0][field] = [] if field == "range_ids" else None
    _save(path, payload)
    with pytest.raises(ValidationError, match=f"group 0.*廃止された項目.*{field}"):
        load_model_config(path)


def test_deprecated_group_detail_field_names_reason(tmp_path: Path) -> None:
    build_project(tmp_path)
    path, payload = _payload(tmp_path)
    payload["group_detail"]["0"]["range_ids"] = [0]
    _save(path, payload)
    with pytest.raises(ValidationError, match="廃止された項目.*range_ids"):
        load_model_config(path)


@pytest.mark.parametrize(
    "command",
    [
        _check_command,
        _train_pre_command,
        _train_command,
        _test_pre_command,
        _test_command,
    ],
)
@pytest.mark.parametrize("range_name", ["noise_std", "perlin_threshold"])
def test_synthetic_anomaly_huge_integer_is_input_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command,
    range_name: str,
) -> None:
    build_project(tmp_path)
    path, payload = _payload(tmp_path)
    payload["group_detail"]["0"]["synthetic_anomaly"] = {
        range_name: {"min": 10**1000, "max": 10**1000}
    }
    _save(path, payload)
    monkeypatch.chdir(tmp_path)
    marker = tmp_path / "data" / "03_check" / "XX" / "all.png"
    marker.parent.mkdir(parents=True)
    marker.write_bytes(b"old")
    with pytest.raises(typer.Exit) as error:
        command(model="XX")
    assert error.value.exit_code == 2
    output = capsys.readouterr()
    assert "synthetic_anomaly" in output.err
    assert "入力不備" in output.err
    assert marker.read_bytes() == b"old"


@pytest.mark.parametrize(
    "command",
    [
        _check_command,
        _train_pre_command,
        _train_command,
        _test_pre_command,
        _test_command,
    ],
)
def test_all_commands_clear_model_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command
) -> None:
    build_project(tmp_path)
    run_id = "a" * 32
    directories = [
        tmp_path / "data/03_check" / f".XX-stage-{run_id}",
        tmp_path / "data/04_train" / f".XX-stage-{run_id}",
        tmp_path / "data/04_train/XX" / f".group_09-stage-{run_id}",
        tmp_path / "data/05_test" / f".XX-stage-{run_id}",
        tmp_path / "data/06_result/XX" / f".stage-{run_id}",
        tmp_path / "optuna/XX" / f".group_09-stage-{run_id}",
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    checkpoint_stage = tmp_path / "weights/XX" / f".group_09.ckpt-stage-{run_id}"
    checkpoint_stage.parent.mkdir(parents=True)
    checkpoint_stage.write_bytes(b"stale")
    config_temp = tmp_path / "config/part_XX.json.tmp"
    config_temp.write_text("stale")
    other_model = tmp_path / "data/03_check" / f".YY-stage-{run_id}"
    other_model.mkdir()
    unmanaged = tmp_path / "data/06_result/XX/notes.txt"
    unmanaged.write_text("safe")
    monkeypatch.chdir(tmp_path)
    with suppress(typer.Exit, ValueError, FileNotFoundError):
        command(model="XX")
    assert all(
        not item.exists() for item in [*directories, checkpoint_stage, config_temp]
    )
    assert other_model.is_dir()
    assert unmanaged.read_text() == "safe"


def test_model_stage_symlink_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_project(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "marker"
    marker.write_text("safe")
    stage = tmp_path / "data/06_result/XX" / f".stage-{'a' * 32}"
    stage.parent.mkdir(parents=True)
    stage.symlink_to(outside, target_is_directory=True)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(typer.Exit) as error:
        _check_command(model="XX")
    assert error.value.exit_code == 2
    assert marker.read_text() == "safe"


def test_per_range_testing_fingerprint(tmp_path: Path) -> None:
    build_project(
        tmp_path, ranges=[{"id": 0, "x": 0, "y": 0}, {"id": 1, "x": 8, "y": 0}]
    )
    path, payload = _payload(tmp_path)
    before = load_config(tmp_path, "XX")
    train_before = preparation_fingerprint(before, group=before.part.groups[0])
    test_before = preparation_fingerprint(before)
    payload["groups"][0]["ranges"][0]["inspection_threshold"] = 0.8
    payload["groups"][0]["ranges"][1]["heatmap_range"] = {"min": -2.0, "max": 3.0}
    _save(path, payload)
    changed = load_config(tmp_path, "XX")
    assert (
        preparation_fingerprint(changed, group=changed.part.groups[0]) == train_before
    )
    assert preparation_fingerprint(changed) == test_before
    payload["groups"][0]["ranges"].pop()
    _save(path, payload)
    changed_membership = load_config(tmp_path, "XX")
    assert preparation_fingerprint(changed_membership) == test_before
    assert (
        preparation_fingerprint(
            changed_membership, group=changed_membership.part.groups[0]
        )
        != train_before
    )


def test_per_range_brightness_fingerprint(tmp_path: Path) -> None:
    build_project(tmp_path)
    path, payload = _payload(tmp_path)
    before = load_config(tmp_path, "XX")
    train_before = preparation_fingerprint(before, group=before.part.groups[0])
    test_before = preparation_fingerprint(before)
    payload["brightness_normalization"] = {"enabled": True, "statistic": "mean"}
    _save(path, payload)
    changed = load_config(tmp_path, "XX")
    assert (
        preparation_fingerprint(changed, group=changed.part.groups[0]) != train_before
    )
    assert preparation_fingerprint(changed) != test_before


@pytest.mark.parametrize("value", [-0.1, 1.1, True, "0.5", float("nan"), float("inf")])
def test_per_range_invalid_threshold_all_commands(
    tmp_path: Path, value: object
) -> None:
    build_project(tmp_path)
    path, payload = _payload(tmp_path)
    payload["groups"][0]["ranges"][0]["inspection_threshold"] = value
    _save(path, payload)
    with pytest.raises(ValidationError, match="group 0 range 0.*inspection_threshold"):
        load_model_config(path)


@pytest.mark.parametrize(
    "value",
    [
        None,
        {"min": 0},
        {"min": 1, "max": 1},
        {"min": 2, "max": 1},
        {"min": True, "max": 1},
        {"min": float("inf"), "max": 1},
    ],
)
def test_per_range_invalid_heatmap_all_commands(tmp_path: Path, value: object) -> None:
    build_project(tmp_path)
    path, payload = _payload(tmp_path)
    payload["groups"][0]["ranges"][0]["heatmap_range"] = value
    _save(path, payload)
    with pytest.raises(ValidationError, match="group 0 range 0.*heatmap_range"):
        load_model_config(path)


def test_req_031_s01_negative_sampler_startup_trials(tmp_path: Path) -> None:
    build_project(tmp_path)
    path, payload = _payload(tmp_path)
    payload["group_detail"]["0"]["optuna_settings"]["sampler"]["startup_trials"] = -1
    _save(path, payload)
    with pytest.raises(ValidationError, match="startup_trials"):
        load_model_config(path)
    assert not (tmp_path / "optuna").exists()


@pytest.mark.parametrize("invalid", [1.5, "5", True])
def test_req_031_s02_noninteger_sampler_startup_trials(
    tmp_path: Path, invalid: object
) -> None:
    build_project(tmp_path)
    path, payload = _payload(tmp_path)
    sampler = payload["group_detail"]["0"]["optuna_settings"]["sampler"]
    sampler["startup_trials"] = invalid
    _save(path, payload)
    with pytest.raises(ValidationError, match="startup_trials"):
        load_model_config(path)
    assert not (tmp_path / "optuna").exists()
    sampler["startup_trials"] = 2
    _save(path, payload)
    assert (
        load_model_config(path)
        .select_groups(0)[0]
        .optuna_settings.sampler.startup_trials
        == 2
    )


@pytest.mark.parametrize(
    "mutation, reason",
    [
        ("empty", "groups"),
        ("duplicate_group", "unique"),
        ("negative_group", "greater than or equal"),
        ("float_group", "integer"),
        ("empty_ranges", "ranges"),
        ("duplicate_range", "range 0 is duplicated"),
        ("unknown_range", "unknown range"),
        ("invalid_threshold", "inspection_threshold"),
    ],
)
def test_group_req_021_s02(tmp_path: Path, mutation: str, reason: str) -> None:
    build_project(tmp_path)
    path, payload = _payload(tmp_path)
    group = payload["groups"][0]
    if mutation == "empty":
        payload["groups"] = []
    elif mutation == "duplicate_group":
        payload["groups"].append(json.loads(json.dumps(group)))
    elif mutation == "negative_group":
        group["id"] = -1
    elif mutation == "float_group":
        group["id"] = 0.5
    elif mutation == "empty_ranges":
        group["ranges"] = []
    elif mutation == "duplicate_range":
        group["ranges"] = [group["ranges"][0], group["ranges"][0]]
    elif mutation == "unknown_range":
        group["ranges"][0]["id"] = 3
    elif mutation == "invalid_threshold":
        group["ranges"][0]["inspection_threshold"] = True
    _save(path, payload)
    with pytest.raises(ValidationError, match=reason):
        load_model_config(path)


def test_group_req_021_s03(tmp_path: Path) -> None:
    build_project(tmp_path)
    path, payload = _payload(tmp_path)
    payload.pop("groups")
    _save(path, payload)
    with pytest.raises(ValidationError, match="groups"):
        load_model_config(path)


@pytest.mark.parametrize("mutation", ["missing", "extra", "padded", "negative"])
def test_group_detail_rejects_mismatched_ids(tmp_path: Path, mutation: str) -> None:
    build_project(tmp_path)
    path, payload = _payload(tmp_path)
    if mutation == "missing":
        payload["group_detail"] = {}
    elif mutation == "extra":
        payload["group_detail"]["1"] = payload["group_detail"]["0"]
    elif mutation == "padded":
        payload["group_detail"]["00"] = payload["group_detail"].pop("0")
    elif mutation == "negative":
        payload["group_detail"]["-1"] = payload["group_detail"].pop("0")
    _save(path, payload)
    with pytest.raises(ValidationError, match="group_detail"):
        load_model_config(path)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("old", "group 0"),
        ("summary_in_detail", "group_detail"),
        ("missing_detail", "group_detail"),
        ("missing_setting", "augmentation"),
    ],
)
def test_group_detail_rejects_mixed_fields(
    tmp_path: Path, mutation: str, reason: str
) -> None:
    build_project(tmp_path)
    path, payload = _payload(tmp_path)
    if mutation == "old":
        payload["groups"][0]["score"] = payload["group_detail"]["0"].pop("score")
    elif mutation == "summary_in_detail":
        payload["group_detail"]["0"]["range_ids"] = [0]
    elif mutation == "missing_detail":
        payload.pop("group_detail")
    else:
        payload["group_detail"]["0"].pop("augmentation")
    _save(path, payload)
    with pytest.raises(ValidationError, match=reason):
        load_model_config(path)


def test_invalid_group_detail_keeps_config(tmp_path: Path) -> None:
    build_project(tmp_path)
    path, payload = _payload(tmp_path)
    payload["group_detail"].pop("0")
    _save(path, payload)
    before = path.read_bytes()
    with pytest.raises(ValidationError, match="group_detail"):
        load_config(tmp_path, "XX")
    with pytest.raises(ValidationError, match="group_detail"):
        write_threshold(path, 0.4, group=0)
    assert path.read_bytes() == before


def test_training_threshold_updates_only_one_group(tmp_path: Path) -> None:
    build_project(tmp_path)
    path, payload = _payload(tmp_path)
    second = json.loads(json.dumps(payload["groups"][0]))
    second["id"] = 1
    payload["groups"].append(second)
    payload["group_detail"]["1"] = json.loads(json.dumps(payload["group_detail"]["0"]))
    payload["groups"][0]["ranges"][0]["inspection_threshold"] = 0.2
    _save(path, payload)
    before = preparation_fingerprint(
        load_config(tmp_path, "XX"), group=load_config(tmp_path, "XX").part.groups[0]
    )
    write_threshold(path, 0.4, group=1)
    updated = load_config(tmp_path, "XX")
    assert updated.part.groups[0].optuna_settings.threshold.value is None
    assert updated.part.groups[1].optuna_settings.threshold.value == 0.4
    raw = json.loads(path.read_text())
    assert raw["group_detail"]["0"]["optuna_settings"]["threshold"]["value"] is None
    assert raw["group_detail"]["1"]["optuna_settings"]["threshold"]["value"] == 0.4
    assert raw["groups"][0]["ranges"][0]["inspection_threshold"] == 0.2
    assert preparation_fingerprint(updated, group=updated.part.groups[0]) == before


def test_test_fingerprint_excludes_training_settings(tmp_path: Path) -> None:
    build_project(tmp_path)
    config = load_config(tmp_path, "XX")
    initial = preparation_fingerprint(config)
    path, payload = _payload(tmp_path)
    payload["group_detail"]["0"]["augmentation"]["seed"] = 99
    payload["blacklist"] = [{"image": "source.png", "id": [0]}]
    _save(path, payload)
    assert preparation_fingerprint(load_config(tmp_path, "XX")) == initial


def test_group_artifact_paths_reject_symlink_alias(tmp_path: Path) -> None:
    _, paths = build_project(tmp_path)
    real = tmp_path / "other-study"
    real.mkdir()
    study = tmp_path / "optuna" / "XX"
    study.parent.mkdir()
    study.symlink_to(real)
    with pytest.raises(ValueError, match="symlink"):
        paths.study_dir("XX", 0)


def _aligned(image, _reference, _settings):
    return AlignedImage(image, 20, 0.8)


def _brightness_images(paths) -> None:
    write_test_image(paths.original_train("XX") / "base.png", value=80)
    write_test_image(paths.original_train("XX") / "a.png", value=40)
    write_test_image(paths.original_test("XX") / "sample.png", value=40)


def test_brightness_defaults(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path)
    assert config.part.brightness_normalization.model_dump() == {
        "enabled": False,
        "statistic": "median",
        "exclude_above": 230,
        "exclude_below": 0,
        "min_gain": 0.5,
        "max_gain": 2.0,
    }
    _brightness_images(paths)
    assert prepare_training(config, paths, aligner=_aligned)[0].sources
    assert prepare_testing(config, paths, aligner=_aligned).sources
    from app.common.image_io import read_image

    assert read_image(paths.prepared_train("XX", 0) / "a_00.png")[0, 0, 0] == 40
    assert read_image(paths.prepared_test("XX") / "sample_00.png")[0, 0, 0] == 40
    disabled_fingerprint = preparation_fingerprint(config, group=config.part.groups[0])
    path, payload = _payload(tmp_path)
    payload["brightness_normalization"] = {"statistic": "mean"}
    _save(path, payload)
    assert load_config(tmp_path, "XX").part.brightness_normalization.model_dump() == {
        **config.part.brightness_normalization.model_dump(),
        "enabled": True,
        "statistic": "mean",
    }
    updated = load_config(tmp_path, "XX")
    assert preparation_fingerprint(updated, group=updated.part.groups[0]) != (
        disabled_fingerprint
    )
    assert prepare_training(updated, paths, aligner=_aligned)[0].sources
    assert prepare_testing(updated, paths, aligner=_aligned).sources
    assert read_image(paths.prepared_train("XX", 0) / "a_00.png")[0, 0, 0] == 80
    assert read_image(paths.prepared_test("XX") / "sample_00.png")[0, 0, 0] == 80


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("enabled", 1, "enabled"),
        ("statistic", "mode", "statistic"),
        ("exclude_above", 0, "exclude_above"),
        ("exclude_above", 256, "exclude_above"),
        ("exclude_below", -1, "exclude_below"),
        ("exclude_below", 255, "exclude_below"),
        ("exclude_below", True, "exclude_below"),
        ("min_gain", 0, "min_gain"),
        ("max_gain", -1, "max_gain"),
        ("min_gain", "0.5", "min_gain"),
        ("max_gain", float("inf"), "max_gain"),
        ("max_gain", 10**400, "max_gain"),
        ("exclude_below", 230, "exclude_below"),
        ("min_gain", 3, "min_gain"),
    ],
)
def test_brightness_rejects_invalid_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    field: str,
    value: object,
    reason: str,
) -> None:
    _, paths = build_project(tmp_path)
    path, payload = _payload(tmp_path)
    payload["brightness_normalization"] = {field: value}
    _save(path, payload)
    target = paths.prepared_test("XX")
    target.mkdir(parents=True)
    marker = target / "old.txt"
    marker.write_text("preserved")
    with pytest.raises(ValidationError, match=reason):
        load_config(tmp_path, "XX")
    assert marker.read_text() == "preserved"
    if field == "min_gain" and value == 3:
        from app.image_preparation.cli import _test_pre_command

        monkeypatch.chdir(tmp_path)
        with pytest.raises(typer.Exit) as error:
            _test_pre_command(model="XX")
        assert getattr(error.value, "exit_code", None) == 2
        output = capsys.readouterr()
        assert reason in output.err
        assert marker.read_text() == "preserved"


def test_brightness_training_fingerprint(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path)
    _brightness_images(paths)
    group = config.part.groups[0]
    manifest = prepare_training(config, paths, group=0, aligner=_aligned)[0]
    assert manifest.preparation_fingerprint == preparation_fingerprint(
        config, group=group
    )
    assert (
        contracts.load_preparation_manifest(
            paths.prepared_train("XX", 0),
            model="XX",
            group=0,
            allowed_split_ids={0},
            fingerprint=preparation_fingerprint(config, group=group),
        )
        == manifest
    )


def test_brightness_testing_fingerprint(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path)
    _brightness_images(paths)
    manifest = prepare_testing(config, paths, aligner=_aligned)
    assert manifest.preparation_fingerprint == preparation_fingerprint(config)
    path, payload = _payload(tmp_path)
    payload["blacklist"] = [{"image": "a.png", "id": [0]}]
    payload["group_detail"]["0"]["augmentation"]["seed"] = 99
    _save(path, payload)
    assert preparation_fingerprint(load_config(tmp_path, "XX")) == (
        manifest.preparation_fingerprint
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("enabled", False),
        ("statistic", "mean"),
        ("exclude_above", 231),
        ("exclude_below", 1),
        ("min_gain", 0.6),
        ("max_gain", 1.9),
    ],
)
def test_brightness_changes_invalidate_preparation(
    tmp_path: Path, field: str, value: object
) -> None:
    _, paths = build_project(tmp_path)
    path, payload = _payload(tmp_path)
    payload["brightness_normalization"] = {}
    _save(path, payload)
    config = load_config(tmp_path, "XX")
    _brightness_images(paths)
    train_manifest = prepare_training(config, paths, group=0, aligner=_aligned)[0]
    test_manifest = prepare_testing(config, paths, aligner=_aligned)
    payload["brightness_normalization"] = {field: value}
    _save(path, payload)
    changed = load_config(tmp_path, "XX")
    for old, new, directory, group in (
        (
            train_manifest.preparation_fingerprint,
            preparation_fingerprint(changed, group=changed.part.groups[0]),
            paths.prepared_train("XX", 0),
            0,
        ),
        (
            test_manifest.preparation_fingerprint,
            preparation_fingerprint(changed),
            paths.prepared_test("XX"),
            None,
        ),
    ):
        assert new != old
        with pytest.raises(ValueError, match="fingerprint mismatch"):
            contracts.load_preparation_manifest(
                directory,
                model="XX",
                group=group,
                allowed_split_ids={0},
                fingerprint=new,
            )
    if field == "enabled":
        baseline = preparation_fingerprint(changed)
        payload["brightness_normalization"]["min_gain"] = 0.7
        _save(path, payload)
        assert preparation_fingerprint(load_config(tmp_path, "XX")) == baseline
