"""Image alignment, crop validation, and range visualization."""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, floor, isfinite, radians, sin
from typing import Any, cast

import cv2
import numpy as np

from app.common.config import (
    AlignmentSettings,
    BrightnessNormalizationSettings,
    CropRange,
    EccAlignmentSettings,
    OrbAlignmentSettings,
)
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
    matches: int | None = None
    inlier_ratio: float | None = None
    correlation: float | None = None
    translation_x: float | None = None
    translation_y: float | None = None
    rotation_degrees: float | None = None
    scale: float | None = None


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
    settings: OrbAlignmentSettings,
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


def align_image(
    image: ImageArray, reference: ImageArray, settings: AlignmentSettings
) -> AlignedImage:
    """Apply the selected model-wide alignment method."""

    if settings.method == "NONE":
        return AlignedImage(image.copy())
    if settings.method == "ORB":
        if settings.orb is None:
            raise AlignmentError("orb_settings_missing")
        return align_orb(image, reference, settings.orb)
    if settings.ecc is None:
        raise AlignmentError("ecc_settings_missing")
    return align_ecc(image, reference, settings.ecc)


def _similarity(
    matrix: np.ndarray, center: np.ndarray
) -> tuple[np.ndarray, float, float]:
    linear = matrix[:, :2].astype(np.float64)
    left, singular, right = np.linalg.svd(linear)
    rotation = left @ right
    if np.linalg.det(rotation) < 0:
        left[:, -1] *= -1
        rotation = left @ right
    scale = float(np.mean(singular))
    angle = float(np.degrees(np.arctan2(rotation[1, 0], rotation[0, 0])))
    mapped_center = linear @ center + matrix[:, 2]
    translation = mapped_center - scale * rotation @ center
    result = np.column_stack((scale * rotation, translation))
    return result, scale, angle


def align_ecc(
    image: ImageArray, reference: ImageArray, settings: EccAlignmentSettings
) -> AlignedImage:
    """Estimate a coarse similarity transform using phase correlation and ECC."""

    ref_height, ref_width = reference.shape[:2]
    reduction = min(1.0, 512 / max(ref_height, ref_width))
    small_width = max(1, round(ref_width * reduction))
    small_height = max(1, round(ref_height * reduction))
    source_small = cv2.resize(
        image,
        (
            max(1, round(image.shape[1] * reduction)),
            max(1, round(image.shape[0] * reduction)),
        ),
        interpolation=cv2.INTER_AREA,
    )
    reference_small = cv2.resize(
        reference, (small_width, small_height), interpolation=cv2.INTER_AREA
    )
    source_canvas = cv2.warpAffine(
        source_small, np.eye(2, 3, dtype=np.float32), (small_width, small_height)
    )
    source_gray = cv2.cvtColor(source_canvas, cv2.COLOR_BGR2GRAY).astype(np.float32)
    reference_gray = cv2.cvtColor(reference_small, cv2.COLOR_BGR2GRAY).astype(
        np.float32
    )
    if np.std(source_gray) < 1 or np.std(reference_gray) < 1:
        raise AlignmentError("insufficient_texture")
    source_gray = cv2.GaussianBlur(source_gray, (5, 5), 0)
    reference_gray = cv2.GaussianBlur(reference_gray, (5, 5), 0)
    window = cv2.createHanningWindow((small_width, small_height), cv2.CV_32F)
    center = np.array([small_width / 2, small_height / 2], dtype=np.float64)
    candidates: list[tuple[float, np.ndarray]] = []
    for scale in np.linspace(settings.min_scale, settings.max_scale, 5):
        for angle in np.linspace(
            -settings.max_rotation_degrees, settings.max_rotation_degrees, 5
        ):
            matrix = cv2.getRotationMatrix2D(tuple(center), float(angle), float(scale))
            rotated = cv2.warpAffine(source_gray, matrix, (small_width, small_height))
            shift, response = cv2.phaseCorrelate(rotated, reference_gray.copy(), window)
            if not (isfinite(shift[0]) and isfinite(shift[1]) and isfinite(response)):
                continue
            matrix[0, 2] += round(shift[0])
            matrix[1, 2] += round(shift[1])
            candidates.append((response, matrix))
    if not candidates:
        raise AlignmentError("ecc_initialization_failed")
    candidates.sort(key=lambda item: item[0], reverse=True)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 75, 1e-5)
    best: tuple[float, np.ndarray, float, float, float, float] | None = None
    out_of_range = False
    for _, candidate in candidates[:5]:
        try:
            inverse = cv2.invertAffineTransform(candidate).astype(np.float32)
            _, estimated_inverse = cv2.findTransformECC(
                reference_gray,
                source_gray,
                inverse,
                cv2.MOTION_AFFINE,
                criteria,
                np.ones_like(reference_gray, dtype=np.uint8),
                5,
            )
            estimated = cv2.invertAffineTransform(estimated_inverse)
            projected, scale, angle = _similarity(estimated, center)
            displacement = projected[:, :2] @ center + projected[:, 2] - center
            dx, dy = float(displacement[0]), float(displacement[1])
            if not all(isfinite(value) for value in (scale, angle, dx, dy)):
                continue
            translation_limit_x = settings.max_translation_ratio * small_width
            translation_limit_y = settings.max_translation_ratio * small_height
            if (
                scale < settings.min_scale - 0.01
                or scale > settings.max_scale + 0.01
                or abs(angle) > settings.max_rotation_degrees + 0.25
                or abs(dx) > translation_limit_x + 1
                or abs(dy) > translation_limit_y + 1
            ):
                out_of_range = True
                continue
            limited_scale = min(max(scale, settings.min_scale), settings.max_scale)
            limited_angle = min(
                max(angle, -settings.max_rotation_degrees),
                settings.max_rotation_degrees,
            )
            limited_dx = min(max(dx, -translation_limit_x), translation_limit_x)
            limited_dy = min(max(dy, -translation_limit_y), translation_limit_y)
            if (limited_scale, limited_angle, limited_dx, limited_dy) != (
                scale,
                angle,
                dx,
                dy,
            ):
                theta = radians(limited_angle)
                linear = limited_scale * np.array(
                    [[cos(theta), -sin(theta)], [sin(theta), cos(theta)]]
                )
                target_center = center + np.array([limited_dx, limited_dy])
                projected = np.column_stack((linear, target_center - linear @ center))
                scale, angle, dx, dy = (
                    limited_scale,
                    limited_angle,
                    limited_dx,
                    limited_dy,
                )
            warped = cv2.warpAffine(source_gray, projected, (small_width, small_height))
            mask = cv2.warpAffine(
                np.full(source_gray.shape, 255, dtype=np.uint8),
                projected,
                (small_width, small_height),
                flags=cv2.INTER_NEAREST,
            )
            if np.count_nonzero(mask) < small_width * small_height / 2:
                continue
            correlation = float(cv2.computeECC(reference_gray, warped, mask))
            if not isfinite(correlation):
                continue
            if best is None or correlation > best[0]:
                best = (correlation, projected, scale, angle, dx, dy)
        except (cv2.error, np.linalg.LinAlgError):
            continue
    if best is None:
        raise AlignmentError(
            "ecc_out_of_range" if out_of_range else "ecc_transform_failed"
        )
    correlation, matrix, scale, angle, dx, dy = best
    correlation = min(max(correlation, -1.0), 1.0)
    if correlation < settings.min_correlation:
        raise AlignmentError("ecc_low_correlation")
    full_matrix = matrix.copy()
    full_matrix[:, 2] /= reduction
    aligned = cv2.warpAffine(image, full_matrix, (ref_width, ref_height))
    return AlignedImage(
        cast(ImageArray, aligned),
        correlation=correlation,
        translation_x=dx / reduction,
        translation_y=dy / reduction,
        rotation_degrees=angle,
        scale=scale,
    )


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


def brightness_statistic(
    image: ImageArray, settings: BrightnessNormalizationSettings
) -> float | None:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    included = gray[(gray >= settings.exclude_below) & (gray < settings.exclude_above)]
    if included.size == 0:
        return None
    if settings.statistic == "median":
        return float(np.median(included))
    return float(np.mean(included))


def normalize_brightness(
    image: ImageArray,
    reference: ImageArray,
    settings: BrightnessNormalizationSettings,
) -> ImageArray:
    """Match a split's brightness to its reference split without mutating inputs."""

    if not settings.enabled:
        return image.copy()
    target = brightness_statistic(reference, settings)
    source = brightness_statistic(image, settings)
    if target is None or source is None or source <= 0:
        return image.copy()
    gain = min(max(target / source, settings.min_gain), settings.max_gain)
    with np.errstate(over="ignore"):
        scaled = np.clip(image.astype(np.float64) * gain, 0, 255)
    return cast(ImageArray, np.floor(scaled + 0.5).astype(np.uint8))


def draw_ranges(image: ImageArray, ranges: list[CropRange], size: int) -> ImageArray:
    output = image.copy()
    height, width = output.shape[:2]
    line_width = min(12, max(2, round(min(size, height, width) / 100)))
    font_scale = min(2.5, max(0.7, min(size, height, width) / 400))
    text_width = max(1, round(font_scale * 2))
    occupied: list[tuple[int, int, int, int]] = []
    for crop in ranges:
        validate_crop(output, crop, size)
        end = (crop.x + size - 1, crop.y + size - 1)
        color = _range_color(crop.id)
        cv2.rectangle(output, (crop.x, crop.y), end, color, line_width)
    for crop in ranges:
        color = _range_color(crop.id)
        label = f"{crop.id:02d}"
        (label_width, label_height), baseline = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, text_width
        )
        pad = max(3, line_width)
        box_width = label_width + 2 * pad
        box_height = label_height + baseline + 2 * pad
        candidates = [
            (crop.x + line_width, crop.y + line_width),
            (crop.x + size - box_width - line_width, crop.y + line_width),
            (crop.x + line_width, crop.y + size - box_height - line_width),
            (
                crop.x + size - box_width - line_width,
                crop.y + size - box_height - line_width,
            ),
        ]
        boxes = [
            (
                min(max(x, 0), max(0, width - box_width)),
                min(max(y, 0), max(0, height - box_height)),
            )
            for x, y in candidates
        ]
        x, y = min(
            boxes,
            key=lambda point: sum(
                max(0, min(point[0] + box_width, right) - max(point[0], left))
                * max(0, min(point[1] + box_height, bottom) - max(point[1], top))
                for left, top, right, bottom in occupied
            ),
        )
        occupied.append((x, y, x + box_width, y + box_height))
        cv2.rectangle(
            output,
            (x, y),
            (min(width - 1, x + box_width), min(height - 1, y + box_height)),
            color,
            -1,
        )
        luminance = 0.114 * color[0] + 0.587 * color[1] + 0.299 * color[2]
        text_color = (0, 0, 0) if luminance > 140 else (255, 255, 255)
        outline_color = (255, 255, 255) if text_color == (0, 0, 0) else (0, 0, 0)
        label_area = output[y : y + box_height + 1, x : x + box_width + 1]
        text_mask = np.zeros(label_area.shape[:2], dtype=np.uint8)
        cv2.putText(
            text_mask,
            label,
            (pad, pad + label_height),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            255,
            text_width,
            cv2.LINE_AA,
        )
        radius = max(1, round(font_scale))
        outline_mask = cv2.dilate(
            text_mask,
            np.ones((2 * radius + 1, 2 * radius + 1), dtype=np.uint8),
        )
        label_area[outline_mask > 0] = outline_color
        alpha = text_mask.astype(np.float32)[:, :, None] / 255
        label_area[:] = np.rint(
            label_area * (1 - alpha) + np.asarray(text_color) * alpha
        ).astype(np.uint8)
    return output


def _range_color(split_id: int) -> tuple[int, int, int]:
    hue = round((split_id * 137.507764) % 360 / 2) % 180
    hsv = np.zeros((1, 1, 3), dtype=np.uint8)
    hsv[0, 0] = (hue, 220, 245)
    bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0, 0]
    return int(bgr[0]), int(bgr[1]), int(bgr[2])
