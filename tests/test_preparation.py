from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from conftest import build_project, write_test_image

from app.imaging import AlignedImage, AlignmentError
from app.preparation import (
    PreparationError,
    create_check_image,
    prepare_testing,
    prepare_training,
)


def identity_aligner(image: np.ndarray, *_args: object) -> AlignedImage:
    return AlignedImage(image.copy(), matches=42, inlier_ratio=0.9)


def test_check_writes_labeled_ranges(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path, ranges=[{"id": 7, "x": 2, "y": 3}])
    write_test_image(paths.original_train("XX") / "base.png")
    target = create_check_image(config, paths)
    output = cv2.imread(str(target))
    assert output is not None
    assert np.any((output[:, :, 2] > 200) & (output[:, :, 1] < 80))


def test_train_pre_aligns_and_crops_images(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path)
    original = write_test_image(paths.original_train("XX") / "base.png")
    write_test_image(paths.original_train("XX") / "normal.png", value=100)
    before = original.copy()
    manifest = prepare_training(config, paths, aligner=identity_aligner)
    assert len(manifest.sources) == 2
    assert all(
        source.splits[0].image.endswith("_00.png") for source in manifest.sources
    )
    restored = cv2.imread(str(paths.original_train("XX") / "base.png"))
    assert restored is not None
    assert np.array_equal(restored, before)


def test_train_pre_excludes_blacklist_entries(tmp_path: Path) -> None:
    config, paths = build_project(
        tmp_path, blacklist=[{"image": "normal.png", "id": [0]}]
    )
    write_test_image(paths.original_train("XX") / "base.png")
    write_test_image(paths.original_train("XX") / "normal.png")
    manifest = prepare_training(config, paths, aligner=identity_aligner)
    normal = next(
        item for item in manifest.sources if item.source_image == "normal.png"
    )
    assert normal.splits == []
    assert any(item.get("reason") == "blacklist" for item in manifest.excluded)


@pytest.mark.parametrize(
    "reason", ["insufficient_matches", "homography_failed", "insufficient_inlier_ratio"]
)
def test_train_pre_warns_and_skips_alignment_failure(
    tmp_path: Path, reason: str
) -> None:
    config, paths = build_project(tmp_path)
    write_test_image(paths.original_train("XX") / "base.png")

    def fail(*_args: object) -> AlignedImage:
        raise AlignmentError(reason, matches=3, inlier_ratio=0.1)

    manifest = prepare_training(config, paths, aligner=fail)
    assert manifest.sources[0].splits == []
    assert manifest.sources[0].alignment.reason == reason
    assert manifest.excluded[0]["reason"] == reason


def test_train_pre_rejects_out_of_bounds_crop_atomically(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path, ranges=[{"id": 0, "x": 20, "y": 20}])
    write_test_image(paths.original_train("XX") / "base.png")
    target = paths.prepared_train("XX")
    target.mkdir(parents=True)
    sentinel = target / "keep.txt"
    sentinel.write_text("old", encoding="utf-8")
    with pytest.raises(PreparationError, match="outside image bounds"):
        prepare_training(config, paths, aligner=identity_aligner)
    assert sentinel.read_text(encoding="utf-8") == "old"


def test_test_pre_does_not_apply_blacklist(tmp_path: Path) -> None:
    config, paths = build_project(
        tmp_path, blacklist=[{"image": "sample.png", "id": [0]}]
    )
    write_test_image(paths.original_train("XX") / "base.png")
    write_test_image(paths.original_test("XX") / "sample.png")
    manifest = prepare_testing(config, paths, aligner=identity_aligner)
    assert len(manifest.sources[0].splits) == 1


@pytest.mark.parametrize(
    "reason", ["insufficient_matches", "homography_failed", "insufficient_inlier_ratio"]
)
def test_test_pre_carries_alignment_failure(tmp_path: Path, reason: str) -> None:
    config, paths = build_project(tmp_path)
    write_test_image(paths.original_train("XX") / "base.png")
    write_test_image(paths.original_test("XX") / "sample.png")

    def fail(*_args: object) -> AlignedImage:
        raise AlignmentError(reason)

    manifest = prepare_testing(config, paths, aligner=fail)
    assert manifest.sources[0].alignment.status == "undetermined"
    assert manifest.sources[0].alignment.reason == reason


def test_test_pre_rejects_out_of_bounds_crop(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path, ranges=[{"id": 0, "x": 30, "y": 0}])
    write_test_image(paths.original_train("XX") / "base.png")
    write_test_image(paths.original_test("XX") / "sample.png")
    with pytest.raises(PreparationError, match="outside image bounds"):
        prepare_testing(config, paths, aligner=identity_aligner)
    assert not paths.prepared_test("XX").exists()
