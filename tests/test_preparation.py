from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from conftest import build_project, write_test_image

from app.common.atomic import recover_directory_swap
from app.common.config import AlignmentSettings
from app.image_preparation.imaging import AlignedImage, AlignmentError, align_orb
from app.image_preparation.preparation import (
    PreparationError,
    alignment_warning,
    create_check_image,
    prepare_testing,
    prepare_training,
)


def identity_aligner(image: np.ndarray, *_args: object) -> AlignedImage:
    return AlignedImage(image.copy(), matches=42, inlier_ratio=0.9)


def test_atomic_directory_recovers_interrupted_swap(tmp_path: Path) -> None:
    target = tmp_path / "derived"
    backup = tmp_path / ".derived.backup"
    backup.mkdir()
    (backup / "keep.txt").write_text("old", encoding="utf-8")

    returned = recover_directory_swap(target)

    assert returned == backup
    assert (target / "keep.txt").read_text(encoding="utf-8") == "old"
    assert not backup.exists()

    backup.mkdir()
    (backup / "old.txt").write_text("old", encoding="utf-8")
    recover_directory_swap(target)
    assert target.is_dir()
    assert not backup.exists()


def test_align_orb_uses_configured_ransac_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rng = np.random.default_rng(42)
    reference = rng.integers(0, 256, size=(256, 256, 3), dtype=np.uint8)
    captured: dict[str, float] = {}

    def find_homography(
        source: np.ndarray,
        target: np.ndarray,
        method: int,
        threshold: float,
        *,
        confidence: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        assert source.shape == target.shape
        assert method == cv2.RANSAC
        captured["threshold"] = threshold
        captured["confidence"] = confidence
        return np.eye(3, dtype=np.float64), np.ones((len(source), 1), dtype=np.uint8)

    monkeypatch.setattr(cv2, "findHomography", find_homography)
    settings = AlignmentSettings(
        minimum_matches=4,
        ransac_reprojection_threshold_px=2.5,
        ransac_confidence=0.9,
        minimum_inlier_ratio=0.75,
    )

    result = align_orb(reference.copy(), reference, settings)

    assert result.matches >= settings.minimum_matches
    assert result.inlier_ratio == 1.0
    assert captured == {"threshold": 2.5, "confidence": 0.9}


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


@pytest.mark.parametrize("testing", [False, True])
def test_crop_error_identifies_source_and_split(tmp_path: Path, testing: bool) -> None:
    config, paths = build_project(tmp_path, ranges=[{"id": 7, "x": 30, "y": 0}])
    write_test_image(paths.original_train("XX") / "base.png")
    prepare = prepare_testing if testing else prepare_training
    if testing:
        write_test_image(paths.original_test("XX") / "sample.png")
        expected_source = "sample.png"
    else:
        expected_source = "base.png"

    with pytest.raises(PreparationError) as captured:
        prepare(config, paths, aligner=identity_aligner)

    message = str(captured.value)
    assert expected_source in message
    assert "range id 7" in message


def test_alignment_warning_identifies_source_reason_and_action() -> None:
    training = alignment_warning("train.png", "insufficient_matches", testing=False)
    testing = alignment_warning("test.png", "homography_failed", testing=True)

    assert "train.png" in training
    assert "insufficient_matches" in training
    assert "manual review is required" in training
    assert "test.png" in testing
    assert "homography_failed" in testing
    assert "undetermined" in testing
    assert "recapture is required" in testing
