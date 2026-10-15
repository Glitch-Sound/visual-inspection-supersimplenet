from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import build_project
from pydantic import ValidationError

from app.common.config import (
    load_config,
    load_model_config,
    preparation_fingerprint,
    write_threshold,
)


def _payload(root: Path) -> tuple[Path, dict]:
    path = root / "config" / "part_XX.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_synthetic_objective_defaults_and_validation(tmp_path: Path) -> None:
    build_project(tmp_path)
    path, payload = _payload(tmp_path)
    settings = payload["group_detail"]["0"]["optuna_settings"]
    assert (
        load_config(tmp_path, "XX").part.groups[0].optuna_settings.objective
        == "normal_percentile"
    )
    for field in ("objective", "synthetic_validation"):
        settings.pop(field, None)
    _save(path, payload)
    assert (
        load_config(tmp_path, "XX").part.groups[0].optuna_settings.objective
        == "normal_percentile"
    )
    for bad in (
        {"types": [], "intensity": 0.5, "seed": 42},
        {"types": ["unknown"], "intensity": 0.5, "seed": 42},
        {"types": ["scratch"], "intensity": 0, "seed": 42},
        {"types": ["scratch"], "intensity": 2, "seed": 42},
    ):
        settings["synthetic_validation"] = bad
        _save(path, payload)
        with pytest.raises(ValidationError, match="synthetic_validation"):
            load_config(tmp_path, "XX")


def test_group_req_021_s01(tmp_path: Path) -> None:
    config, _ = build_project(
        tmp_path, ranges=[{"id": 0, "x": 0, "y": 0}, {"id": 1, "x": 8, "y": 0}]
    )
    path, payload = _payload(tmp_path)
    second = json.loads(json.dumps(payload["groups"][0]))
    second["id"] = 1
    second["range_ids"] = [0]
    payload["groups"][0]["range_ids"] = [0, 1]
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


@pytest.mark.parametrize(
    "mutation, reason",
    [
        ("empty", "groups"),
        ("duplicate_group", "unique"),
        ("negative_group", "greater than or equal"),
        ("float_group", "integer"),
        ("empty_ranges", "range_ids"),
        ("duplicate_range", "unique"),
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
        group["range_ids"] = []
    elif mutation == "duplicate_range":
        group["range_ids"] = [0, 0]
    elif mutation == "unknown_range":
        group["range_ids"] = [3]
    elif mutation == "invalid_threshold":
        group["inspection_threshold"] = True
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
        ("old", "groups"),
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
    payload["groups"][0]["inspection_threshold"] = 0.2
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
    assert raw["groups"][0]["inspection_threshold"] == 0.2
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


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [("transform_model", "affine"), ("border_mode", "reflect")],
)
def test_alignment_choices_rejected(tmp_path: Path, field: str, bad_value: str) -> None:
    build_project(tmp_path)
    path, payload = _payload(tmp_path)
    assert load_config(tmp_path, "XX").part.alignment.transform_model == "homography"
    assert load_config(tmp_path, "XX").part.alignment.border_mode == "black"
    payload["alignment"][field] = bad_value
    _save(path, payload)
    before = path.read_bytes()
    with pytest.raises(ValidationError, match=field):
        load_config(tmp_path, "XX")
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("unit", "minimum"),
    [("unknown", 2), ("split", None), ("split", 0), ("split", True), ("split", 1.5)],
)
def test_split_threshold_settings_rejected(
    tmp_path: Path, unit: object, minimum: object
) -> None:
    build_project(tmp_path)
    path, payload = _payload(tmp_path)
    threshold = payload["group_detail"]["0"]["optuna_settings"]["threshold"]
    threshold.update(unit=unit, min_score_count=minimum)
    threshold["method"] = "out_of_fold_percentile"
    threshold["folds"] = 2
    _save(path, payload)
    before = path.read_bytes()
    with pytest.raises(ValidationError):
        load_config(tmp_path, "XX")
    assert path.read_bytes() == before


def test_split_threshold_requires_oof(tmp_path: Path) -> None:
    build_project(tmp_path)
    path, payload = _payload(tmp_path)
    threshold = payload["group_detail"]["0"]["optuna_settings"]["threshold"]
    threshold.update(unit="split", min_score_count=2)
    _save(path, payload)
    with pytest.raises(ValidationError, match="out_of_fold_percentile"):
        load_config(tmp_path, "XX")


def test_group_artifact_paths_reject_symlink_alias(tmp_path: Path) -> None:
    _, paths = build_project(tmp_path)
    real = tmp_path / "other-study"
    real.mkdir()
    study = tmp_path / "optuna" / "XX"
    study.parent.mkdir()
    study.symlink_to(real)
    with pytest.raises(ValueError, match="symlink"):
        paths.study_dir("XX", 0)
