from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from conftest import build_project, write_test_image

from app.common.config import load_config, preparation_fingerprint
from app.common.image_io import ImageReadError
from app.image_preparation.imaging import AlignedImage, AlignmentError
from app.image_preparation.preparation import (
    PreparationError,
    create_check_image,
    prepare_testing,
    prepare_training,
)


def aligned(
    image: np.ndarray, _reference: np.ndarray, _settings: object
) -> AlignedImage:
    return AlignedImage(image, 20, 0.8)


def _two_groups(root: Path):
    config, paths = build_project(
        root,
        ranges=[{"id": 0, "x": 0, "y": 0}, {"id": 1, "x": 8, "y": 0}],
    )
    path = paths.model_config("XX")
    payload = json.loads(path.read_text())
    second = json.loads(json.dumps(payload["groups"][0]))
    second["id"] = 1
    second["range_ids"] = [0]
    payload["groups"].append(second)
    path.write_text(json.dumps(payload))
    return load_config(root, "XX"), paths


def _train_images(paths) -> None:
    for name in ("base.png", "a.png", "b.png"):
        write_test_image(paths.original_train("XX") / name, size=32)


def test_group_req_001_s01(tmp_path: Path) -> None:
    config, paths = _two_groups(tmp_path)
    _train_images(paths)
    assert create_check_image(config, paths) == paths.check_image("XX")
    assert paths.check_image("XX").is_file()
    assert paths.check_image("XX", 0).is_file()
    assert paths.check_image("XX", 1).is_file()


def test_group_req_001_s02(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path, ranges=[{"id": 0, "x": 30, "y": 0}])
    _train_images(paths)
    with pytest.raises(ValueError, match="range|bounds|image"):
        create_check_image(config, paths)
    assert not paths.check_image("XX").exists()


def test_group_req_001_s03(tmp_path: Path) -> None:
    _, paths = build_project(tmp_path)
    payload = json.loads(paths.model_config("XX").read_text())
    payload["base"] = "../outside.png"
    paths.model_config("XX").write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="base"):
        load_config(tmp_path, "XX")


def test_group_req_001_s04(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config, paths = build_project(
        tmp_path,
        image_size=500,
        ranges=[{"id": 0, "x": 400, "y": 0}, {"id": 1, "x": 401, "y": 0}],
    )
    (tmp_path / "config" / "setting.ini").write_text(
        "[IMAGE]\nSIZE = 500\nRESIZE = 0.5\n"
    )
    config = load_config(tmp_path, "XX")
    write_test_image(paths.original_train("XX") / "base.png", size=1500)
    captured = []
    from app.image_preparation import preparation

    original = preparation.draw_ranges

    def capture(image, ranges, size):
        captured.extend(ranges)
        return original(image, ranges, size)

    monkeypatch.setattr(preparation, "draw_ranges", capture)
    create_check_image(config, paths)
    assert [item.x for item in captured[:2]] == [200, 201]


def test_group_req_001_s05(tmp_path: Path) -> None:
    config, paths = _two_groups(tmp_path)
    _train_images(paths)
    create_check_image(config, paths)
    assert (
        paths.check_image("XX", 0).read_bytes()
        != paths.check_image("XX", 1).read_bytes()
    )


def test_group_req_002_s01(tmp_path: Path) -> None:
    config, paths = _two_groups(tmp_path)
    _train_images(paths)
    result = prepare_training(config, paths, aligner=aligned)
    assert set(result) == {0, 1}
    assert (paths.prepared_train("XX", 0) / "a_01.png").is_file()
    assert (paths.prepared_train("XX", 1) / "a_00.png").is_file()


def test_group_req_002_s02(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path, blacklist=[{"image": "a.png", "id": [0]}])
    _train_images(paths)
    result = prepare_training(config, paths, aligner=aligned)[0]
    assert not (paths.prepared_train("XX", 0) / "a_00.png").exists()
    assert any(item["reason"] == "blacklist" for item in result.excluded)


def test_group_req_002_s03(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path)
    _train_images(paths)

    def fail(_image, _reference, _settings):
        raise AlignmentError("too few matches")

    result = prepare_training(config, paths, aligner=fail)[0]
    assert all(not source.splits for source in result.sources)
    assert result.excluded[0]["reason"] == "too few matches"


def test_group_req_002_s04(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path, ranges=[{"id": 0, "x": 30, "y": 0}])
    _train_images(paths)
    with pytest.raises(PreparationError, match="a.png"):
        prepare_training(config, paths, aligner=aligned)
    assert not paths.prepared_train("XX", 0).exists()


def test_group_req_002_s05(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path)
    _train_images(paths)
    prepare_training(config, paths, aligner=aligned)
    marker = paths.prepared_train("XX", 0) / "marker"
    marker.write_text("old")
    (paths.original_train("XX") / "a.png").write_bytes(b"bad image")
    with pytest.raises(ImageReadError, match="a.png"):
        prepare_training(config, paths, aligner=aligned)
    assert marker.read_text() == "old"


def test_group_req_002_s06(tmp_path: Path) -> None:
    _, paths = build_project(tmp_path)
    payload = json.loads(paths.model_config("XX").read_text())
    payload["alignment"]["knn_k"] = 3
    paths.model_config("XX").write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="knn_k"):
        load_config(tmp_path, "XX")


def test_group_req_002_s07(tmp_path: Path) -> None:
    config, paths = _two_groups(tmp_path)
    _train_images(paths)
    prepare_training(config, paths, aligner=aligned)
    marker = paths.prepared_train("XX", 1) / "marker"
    marker.write_text("preserved")
    prepare_training(config, paths, group=0, aligner=aligned)
    assert marker.read_text() == "preserved"


def test_group_req_002_s08(tmp_path: Path) -> None:
    config, paths = _two_groups(tmp_path)
    _train_images(paths)
    prepare_training(config, paths, aligner=aligned)
    assert (paths.prepared_train("XX", 0) / "a_00.png").read_bytes() == (
        paths.prepared_train("XX", 1) / "a_00.png"
    ).read_bytes()


def test_group_req_025_s01(tmp_path: Path) -> None:
    config, paths = _two_groups(tmp_path)
    _train_images(paths)
    manifest = prepare_training(config, paths, group=1, aligner=aligned)[1]
    assert manifest.group == 1
    assert manifest.range_ids == [0]
    assert manifest.preparation_fingerprint == preparation_fingerprint(
        config, group=config.part.groups[1]
    )


def test_group_req_025_s02(tmp_path: Path) -> None:
    config, paths = _two_groups(tmp_path)
    _train_images(paths)
    write_test_image(paths.original_test("XX") / "sample.png", size=32)
    manifest = prepare_testing(config, paths, aligner=aligned)
    assert {
        split.split_id for source in manifest.sources for split in source.splits
    } == {0, 1}
    assert manifest.preparation_fingerprint == preparation_fingerprint(config)
