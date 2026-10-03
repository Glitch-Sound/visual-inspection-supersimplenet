"""Atomic image preparation workflows."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from app.atomic import recover_directory_swap
from app.config import AppConfig, CropRange, validate_blacklist_images
from app.contracts import (
    AlignmentResult,
    PreparationManifest,
    PreparedSource,
    PreparedSplit,
)
from app.imaging import (
    AlignedImage,
    AlignmentError,
    ImageArray,
    align_orb,
    crop_image,
    draw_ranges,
    read_image,
    write_image,
)
from app.paths import ProjectPaths

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
Aligner = Callable[[ImageArray, ImageArray, object], AlignedImage]


class PreparationError(RuntimeError):
    """Raised when valid inputs fail during derived-image generation."""


def _prepared_crop(
    image: ImageArray, crop: CropRange, size: int, *, source_image: str
) -> ImageArray:
    try:
        return crop_image(image, crop, size)
    except ValueError as error:
        raise PreparationError(f"{source_image}: {error}") from error


def alignment_warning(source_image: str, reason: str, *, testing: bool) -> str:
    """Return the complete operator action for an alignment failure."""

    if testing:
        return (
            f"{source_image}: alignment failed ({reason}); result will be "
            "undetermined and recapture is required"
        )
    return (
        f"{source_image}: alignment failed ({reason}); excluded from training "
        "and manual review is required"
    )


def list_images(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise ValueError(f"image directory not found: {directory}")
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def _atomic_replace_directory(target: Path, populate: Callable[[Path], None]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = recover_directory_swap(target)
    stage = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent))
    try:
        populate(stage)
        if target.exists():
            target.replace(backup)
        stage.replace(target)
        if backup.exists():
            shutil.rmtree(backup)
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        if backup.exists() and not target.exists():
            backup.replace(target)
        raise


def create_check_image(config: AppConfig, paths: ProjectPaths) -> Path:
    base_path = paths.original_train(config.model) / config.part.base
    reference = read_image(base_path)
    output = draw_ranges(reference, config.part.ranges, config.image_size)
    target = paths.check_image(config.model)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp.png")
    try:
        write_image(temporary, output)
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def prepare_training(
    config: AppConfig,
    paths: ProjectPaths,
    *,
    aligner: Callable[..., AlignedImage] = align_orb,
) -> PreparationManifest:
    source_dir = paths.original_train(config.model)
    images = list_images(source_dir)
    validate_blacklist_images(config, {path.name for path in images})
    reference = read_image(source_dir / config.part.base)
    blacklist = {
        (entry.image, split_id)
        for entry in config.part.blacklist
        for split_id in entry.id
    }
    manifest: PreparationManifest | None = None

    def populate(stage: Path) -> None:
        nonlocal manifest
        sources: list[PreparedSource] = []
        excluded: list[dict[str, object]] = []
        for source_path in images:
            source = read_image(source_path)
            try:
                aligned = aligner(source, reference, config.part.alignment)
            except AlignmentError as error:
                sources.append(
                    PreparedSource(
                        source_image=source_path.name,
                        alignment=AlignmentResult(
                            status="failed",
                            reason=error.reason,
                            matches=error.matches,
                            inlier_ratio=error.inlier_ratio,
                        ),
                    )
                )
                excluded.append(
                    {"source_image": source_path.name, "reason": error.reason}
                )
                continue
            splits: list[PreparedSplit] = []
            for crop in config.part.ranges:
                if (source_path.name, crop.id) in blacklist:
                    excluded.append(
                        {
                            "source_image": source_path.name,
                            "split_id": crop.id,
                            "reason": "blacklist",
                        }
                    )
                    continue
                split = _prepared_crop(
                    aligned.image,
                    crop,
                    config.image_size,
                    source_image=source_path.name,
                )
                filename = f"{source_path.stem}_{crop.id:02d}{source_path.suffix}"
                write_image(stage / filename, split)
                splits.append(
                    PreparedSplit(
                        source_image=source_path.name,
                        split_id=crop.id,
                        image=filename,
                    )
                )
            sources.append(
                PreparedSource(
                    source_image=source_path.name,
                    alignment=AlignmentResult(
                        status="aligned",
                        matches=aligned.matches,
                        inlier_ratio=aligned.inlier_ratio,
                    ),
                    splits=splits,
                )
            )
        manifest = PreparationManifest(
            model=config.model,
            created_at=datetime.now(UTC),
            sources=sources,
            excluded=excluded,
        )
        manifest.write_json(stage / "manifest.json")

    _atomic_replace_directory(paths.prepared_train(config.model), populate)
    if manifest is None:  # pragma: no cover - defensive invariant
        raise RuntimeError("training manifest was not created")
    return manifest


def prepare_testing(
    config: AppConfig,
    paths: ProjectPaths,
    *,
    aligner: Callable[..., AlignedImage] = align_orb,
) -> PreparationManifest:
    source_dir = paths.original_test(config.model)
    images = list_images(source_dir)
    reference = read_image(paths.original_train(config.model) / config.part.base)
    manifest: PreparationManifest | None = None

    def populate(stage: Path) -> None:
        nonlocal manifest
        sources: list[PreparedSource] = []
        for source_path in images:
            source = read_image(source_path)
            try:
                aligned = aligner(source, reference, config.part.alignment)
            except AlignmentError as error:
                sources.append(
                    PreparedSource(
                        source_image=source_path.name,
                        alignment=AlignmentResult(
                            status="undetermined",
                            reason=error.reason,
                            matches=error.matches,
                            inlier_ratio=error.inlier_ratio,
                        ),
                    )
                )
                continue
            splits: list[PreparedSplit] = []
            for crop in config.part.ranges:
                split = _prepared_crop(
                    aligned.image,
                    crop,
                    config.image_size,
                    source_image=source_path.name,
                )
                filename = f"{source_path.stem}_{crop.id:02d}{source_path.suffix}"
                write_image(stage / filename, split)
                splits.append(
                    PreparedSplit(
                        source_image=source_path.name,
                        split_id=crop.id,
                        image=filename,
                    )
                )
            sources.append(
                PreparedSource(
                    source_image=source_path.name,
                    alignment=AlignmentResult(
                        status="aligned",
                        matches=aligned.matches,
                        inlier_ratio=aligned.inlier_ratio,
                    ),
                    splits=splits,
                )
            )
        manifest = PreparationManifest(
            model=config.model,
            created_at=datetime.now(UTC),
            sources=sources,
        )
        manifest.write_json(stage / "manifest.json")

    _atomic_replace_directory(paths.prepared_test(config.model), populate)
    if manifest is None:  # pragma: no cover
        raise RuntimeError("testing manifest was not created")
    return manifest
