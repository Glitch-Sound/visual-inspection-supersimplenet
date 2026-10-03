"""Image alignment, crop validation, and visualization primitives."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import cv2
import numpy as np
from numpy.typing import NDArray

from app.config import AlignmentSettings, CropRange

ImageArray = NDArray[np.uint8]


class AlignmentError(RuntimeError):
    """Raised when an image cannot satisfy the alignment contract."""

    def __init__(self, reason: str, *, matches: int = 0, inlier_ratio: float = 0.0):
        super().__init__(reason)
        self.reason = reason
        self.matches = matches
        self.inlier_ratio = inlier_ratio


@dataclass(frozen=True)
class AlignedImage:
    image: ImageArray
    matches: int
    inlier_ratio: float


def read_image(path: Path) -> ImageArray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"image cannot be read: {path.name}")
    return cast(ImageArray, image)


def align_orb(
    image: ImageArray,
    reference: ImageArray,
    settings: AlignmentSettings,
) -> AlignedImage:
    """Align ``image`` to ``reference`` using the configured ORB/RANSAC contract."""

    source_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    reference_gray = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY)
    orb = cast(Any, cv2).ORB_create(nfeatures=5000)
    source_keypoints, source_descriptors = orb.detectAndCompute(source_gray, None)
    reference_keypoints, reference_descriptors = orb.detectAndCompute(
        reference_gray, None
    )
    if source_descriptors is None or reference_descriptors is None:
        raise AlignmentError("insufficient_matches")
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = sorted(
        matcher.match(source_descriptors, reference_descriptors),
        key=lambda match: match.distance,
    )
    count = len(matches)
    if count < settings.minimum_matches:
        raise AlignmentError("insufficient_matches", matches=count)

    source_points = np.asarray(
        [source_keypoints[match.queryIdx].pt for match in matches], dtype=np.float32
    ).reshape(-1, 1, 2)
    reference_points = np.asarray(
        [reference_keypoints[match.trainIdx].pt for match in matches], dtype=np.float32
    ).reshape(-1, 1, 2)
    homography, mask = cv2.findHomography(
        source_points,
        reference_points,
        cv2.RANSAC,
        settings.ransac_reprojection_threshold_px,
        confidence=settings.ransac_confidence,
    )
    if homography is None or mask is None:
        raise AlignmentError("homography_failed", matches=count)
    inlier_ratio = float(mask.ravel().mean())
    if inlier_ratio < settings.minimum_inlier_ratio:
        raise AlignmentError(
            "insufficient_inlier_ratio", matches=count, inlier_ratio=inlier_ratio
        )
    height, width = reference.shape[:2]
    aligned = cv2.warpPerspective(image, homography, (width, height))
    return AlignedImage(cast(ImageArray, aligned), count, inlier_ratio)


def validate_crop(image: ImageArray, crop: CropRange, size: int) -> None:
    height, width = image.shape[:2]
    if crop.x + size > width or crop.y + size > height:
        raise ValueError(
            f"range id {crop.id} is outside image bounds: "
            f"[{crop.x},{crop.x + size}) x [{crop.y},{crop.y + size}) "
            f"for {width}x{height}"
        )


def crop_image(image: ImageArray, crop: CropRange, size: int) -> ImageArray:
    validate_crop(image, crop, size)
    return image[crop.y : crop.y + size, crop.x : crop.x + size].copy()


def draw_ranges(image: ImageArray, ranges: list[CropRange], size: int) -> ImageArray:
    output = image.copy()
    for crop in ranges:
        validate_crop(output, crop, size)
        end = (crop.x + size - 1, crop.y + size - 1)
        cv2.rectangle(output, (crop.x, crop.y), end, (0, 0, 255), 2)
        cv2.putText(
            output,
            f"{crop.id:02d}",
            (crop.x + 4, crop.y + 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
    return output


def write_image(path: Path, image: ImageArray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), image):
        raise OSError(f"image write failed: {path.name}")
