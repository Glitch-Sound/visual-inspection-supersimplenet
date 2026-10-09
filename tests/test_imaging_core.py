from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.common.atomic import recover_directory_swap
from app.common.config import AlignmentSettings
from app.image_preparation.imaging import AlignmentError, align_orb


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


def test_align_orb_filters_knn_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    rng = np.random.default_rng(42)
    reference = rng.integers(0, 256, size=(256, 256, 3), dtype=np.uint8)
    captured: dict[str, object] = {}

    class Matcher:
        def knnMatch(
            self, _source: np.ndarray, _target: np.ndarray, *, k: int
        ) -> list[list[cv2.DMatch]]:
            captured["k"] = k
            return [
                [cv2.DMatch(i, i, 0, 10), cv2.DMatch(i, i + 1, 0, 20)]
                for i in range(10)
            ] + [
                [cv2.DMatch(10, 10, 0, 15), cv2.DMatch(10, 11, 0, 20)],
                [cv2.DMatch(11, 11, 0, 10)],
            ]

    def matcher_factory(norm: int, *, crossCheck: bool) -> Matcher:
        assert norm == cv2.NORM_HAMMING
        captured["cross_check"] = crossCheck
        return Matcher()

    def find_homography(
        source: np.ndarray,
        _target: np.ndarray,
        _method: int,
        _threshold: float,
        *,
        confidence: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        assert confidence == 0.95
        captured["points"] = len(source)
        return np.eye(3), np.ones((len(source), 1), dtype=np.uint8)

    monkeypatch.setattr(cv2, "BFMatcher", matcher_factory)
    monkeypatch.setattr(cv2, "findHomography", find_homography)
    result = align_orb(reference.copy(), reference, AlignmentSettings())
    assert result.matches == 10
    assert captured == {"k": 2, "cross_check": False, "points": 10}
    with pytest.raises(AlignmentError, match="insufficient_matches") as error:
        align_orb(
            reference.copy(),
            reference,
            AlignmentSettings(minimum_matches=11),
        )
    assert error.value.matches == 10
