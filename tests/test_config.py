from __future__ import annotations

import json
from configparser import ConfigParser
from pathlib import Path

import pytest
from conftest import build_project, write_test_image
from pydantic import ValidationError

from app.common.config import (
    BlurSettings,
    ExecutionSettings,
    PrunerSettings,
    load_config,
    load_image_settings,
    load_image_size,
    load_model_config,
    write_threshold,
)
from app.common.paths import ProjectPaths
from app.image_preparation.preparation import create_check_image


def test_training_template_matches_defaults() -> None:
    root = Path(__file__).parents[1]
    part = load_model_config(root / "config" / "part_XX.json")
    fixture = load_model_config(root / "tests" / "fixtures" / "model_config.json")

    for model in (part, fixture):
        assert model.optuna_settings.search.epochs.choices == [100, 200, 300]
        assert model.optuna_settings.pruner.startup_trials == 5
        assert model.optuna_settings.pruner.warmup_epochs == 40
        assert model.optuna_settings.pruner.interval_epochs == 10
        assert model.optuna_settings.execution.trials == 10
        assert model.augmentation.blur.enabled is False

    assert PrunerSettings().warmup_epochs == 40
    assert ExecutionSettings().trials == 10
    assert BlurSettings(probability=0.2, kernel_sizes=[3, 5]).enabled is False
    assert PrunerSettings(warmup_epochs=50).warmup_epochs == 50
    assert ExecutionSettings(trials=50).trials == 50


@pytest.mark.parametrize("value", ["10.5", "0", "-1", "500 # comment"])
def test_check_rejects_invalid_ranges(tmp_path: Path, value: str) -> None:
    config, paths = build_project(tmp_path)
    paths.global_config.write_text(f"[IMAGE]\nSIZE = {value}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="IMAGE.SIZE"):
        load_image_size(paths.global_config)

    paths.global_config.write_text("[IMAGE]\nSIZE = 8\n", encoding="utf-8")
    payload = json.loads(paths.model_config("XX").read_text(encoding="utf-8"))
    payload["range"].append(payload["range"][0])
    paths.model_config("XX").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValidationError, match="range.id"):
        load_config(tmp_path, "XX")

    with pytest.raises(ValueError, match="model must match"):
        ProjectPaths(tmp_path).model_config("../XX")

    write_test_image(paths.original_train("XX") / "base.png")
    create_check_image(config, paths)
    existing = paths.check_image("XX").read_bytes()
    invalid = config.model_copy(
        update={
            "part": config.part.model_copy(
                update={"ranges": [config.part.ranges[0].model_copy(update={"x": 99})]}
            )
        }
    )
    with pytest.raises(ValueError, match="outside image bounds"):
        create_check_image(invalid, paths)
    assert paths.check_image("XX").read_bytes() == existing


def test_setting_ini_warns_about_unknown_entries(tmp_path: Path) -> None:
    path = tmp_path / "setting.ini"
    path.write_text(
        "[IMAGE]\nSIZE = 500\nUNKNOWN = value\n[EXTRA]\nVALUE = 1\n",
        encoding="utf-8",
    )

    with pytest.warns(UserWarning, match="unknown entries") as captured:
        assert load_image_size(path) == 500

    message = str(captured[0].message)
    assert "EXTRA" in message
    assert "unknown" in message


@pytest.mark.parametrize("value", ["0", "-0.1", "1.01", "nan", "inf", "text"])
def test_resize_rejects_invalid_values(tmp_path: Path, value: str) -> None:
    config, paths = build_project(tmp_path)
    paths.global_config.write_text(
        f"[IMAGE]\nSIZE = {config.image_size}\nRESIZE = {value}\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="IMAGE.RESIZE"):
        load_config(tmp_path, "XX")


def test_distributed_image_and_alignment_settings_are_present() -> None:
    root = Path(__file__).parents[1]
    parser = ConfigParser()
    assert parser.read(root / "config" / "setting.ini", encoding="utf-8")
    assert {"size", "resize"} <= set(parser["IMAGE"])
    load_image_settings(root / "config" / "setting.ini")

    path = root / "config" / "part_XX.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert {
        "method",
        "knn_k",
        "ratio_threshold",
        "minimum_matches",
        "ransac_reprojection_threshold_px",
        "ransac_confidence",
        "minimum_inlier_ratio",
    } <= set(payload["alignment"])
    load_model_config(path)


def test_alignment_knn_settings_validation(tmp_path: Path) -> None:
    _, paths = build_project(tmp_path)
    payload = json.loads(paths.model_config("XX").read_text(encoding="utf-8"))
    for key, value in [("knn_k", 3), ("ratio_threshold", 0), ("ratio_threshold", 1)]:
        payload["alignment"][key] = value
        paths.model_config("XX").write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValidationError, match=key):
            load_config(tmp_path, "XX")
        payload["alignment"].pop(key)


@pytest.mark.parametrize(
    "base",
    [
        "<absolute>",
        "../base.png",
        "nested/base.png",
        "nested\\base.png",
        "C:\\base.png",
        ".",
        "..",
    ],
)
def test_base_rejects_paths_outside_model_root(tmp_path: Path, base: str) -> None:
    _config, paths = build_project(tmp_path)
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"unchanged")
    if base == "<absolute>":
        base = str(outside.resolve())
    payload = json.loads(paths.model_config("XX").read_text(encoding="utf-8"))
    payload["base"] = base
    paths.model_config("XX").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValidationError, match="base"):
        load_config(tmp_path, "XX")

    assert outside.read_bytes() == b"unchanged"


def test_inspection_threshold_is_preserved_when_training_threshold_changes(
    tmp_path: Path,
) -> None:
    _config, paths = build_project(tmp_path)
    path = paths.model_config("XX")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["inspection_threshold"] = 0.25
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_config(tmp_path, "XX").part.inspection_threshold == 0.25
    write_threshold(path, 0.6)
    updated = load_config(tmp_path, "XX").part
    assert updated.inspection_threshold == 0.25
    assert updated.optuna_settings.threshold.value == 0.6
