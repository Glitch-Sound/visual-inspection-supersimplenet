"""Image alignment, crop validation, and range visualization."""

from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Any, cast

import cv2
import numpy as np

from app.common.config import AlignmentSettings, CropRange
from app.common.image_io import ImageArray


class AlignmentError(RuntimeError):
    """Raised when an image cannot satisfy the alignment contract."""

    def __init__(self, reason: str, *, matches: int = 0, inlier_ratio: float = 0.0):
        super().__init__(reason)
        self.reason = reason
        self.matches = matches
        self.inlier_ratio = inlier_ratio


class ImageResizeError(RuntimeError):
    """Raised when a valid scale makes an image too small to process."""


@dataclass(frozen=True)
class AlignedImage:
    image: ImageArray
    matches: int
    inlier_ratio: float


def resize_image(image: ImageArray, scale: float) -> ImageArray:
    """Downsample before alignment while retaining the source image."""

    if scale == 1.0:
        return image
    height, width = image.shape[:2]
    if round(width * scale) < 1 or round(height * scale) < 1:
        raise ImageResizeError("IMAGE.RESIZE makes the image dimension zero")
    return cast(
        ImageArray,
        cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA),
    )


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
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    matches = sorted(
        (
            candidates[0]
            for candidates in matcher.knnMatch(
                source_descriptors, reference_descriptors, k=settings.knn_k
            )
            if len(candidates) == settings.knn_k
            and candidates[0].distance
            < settings.ratio_threshold * candidates[1].distance
        ),
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


def scaled_crop_range(
    image: ImageArray, crop: CropRange, size: int, scale: float
) -> CropRange:
    """Map a range on the original reference to the resized image."""

    scaled = CropRange(
        id=crop.id,
        x=floor(crop.x * scale + 0.5),
        y=floor(crop.y * scale + 0.5),
    )
    validate_crop(image, scaled, size)
    return scaled


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
