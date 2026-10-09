"""Atomic image preparation workflows."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from app.common.atomic import recover_directory_swap
from app.common.config import (
    AppConfig,
    CropRange,
    preparation_fingerprint,
    validate_blacklist_images,
)
from app.common.contracts import (
    AlignmentResult,
    PreparationManifest,
    PreparedSource,
    PreparedSplit,
)
from app.common.image_io import ImageArray, read_image, write_image
from app.common.paths import ProjectPaths
from app.image_preparation.imaging import (
    AlignedImage,
    AlignmentError,
    align_orb,
    crop_image,
    draw_ranges,
    resize_image,
    scaled_crop_range,
)

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
Aligner = Callable[[ImageArray, ImageArray, object], AlignedImage]
ProgressCallback = Callable[[int, int], None]


class PreparationError(RuntimeError):
    """Raised when valid inputs fail during derived-image generation."""


def _prepared_crop(
    image: ImageArray,
    crop: CropRange,
    size: int,
    scale: float,
    *,
    source_image: str,
) -> ImageArray:
    try:
        return crop_image(image, scaled_crop_range(image, crop, size, scale), size)
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
    reference = resize_image(read_image(base_path), config.image_resize)
    ranges = [
        scaled_crop_range(reference, crop, config.image_size, config.image_resize)
        for crop in config.part.ranges
    ]
    selected = [(None, ranges)] + [
        (group.id, [item for item in ranges if item.id in group.range_ids])
        for group in config.part.select_groups()
    ]
    target_dir = paths.check_image(config.model).parent

    def populate(stage: Path) -> None:
        for group_id, selected_ranges in selected:
            name = "all.png" if group_id is None else f"group_{group_id}.png"
            write_image(
                stage / name, draw_ranges(reference, selected_ranges, config.image_size)
            )

    _atomic_replace_directory(target_dir, populate)
    return paths.check_image(config.model)


def prepare_training(
    config: AppConfig,
    paths: ProjectPaths,
    *,
    aligner: Callable[..., AlignedImage] = align_orb,
    on_progress: ProgressCallback | None = None,
    group: int | None = None,
) -> dict[int, PreparationManifest]:
    source_dir = paths.original_train(config.model)
    images = list_images(source_dir)
    if on_progress is not None:
        on_progress(0, len(images))
    validate_blacklist_images(config, {path.name for path in images})
    reference = resize_image(
        read_image(source_dir / config.part.base), config.image_resize
    )
    blacklist = {
        (entry.image, split_id)
        for entry in config.part.blacklist
        for split_id in entry.id
    }
    groups = config.part.select_groups(group)
    manifests: dict[int, PreparationManifest] = {}

    def populate(stage: Path) -> None:
        sources: dict[int, list[PreparedSource]] = {item.id: [] for item in groups}
        excluded: dict[int, list[dict[str, object]]] = {item.id: [] for item in groups}
        targets = {
            item.id: stage if group is not None else stage / f"group_{item.id}"
            for item in groups
        }
        for target in targets.values():
            target.mkdir(parents=True, exist_ok=True)
        for index, source_path in enumerate(images, start=1):
            source = resize_image(read_image(source_path), config.image_resize)
            try:
                aligned = aligner(source, reference, config.part.alignment)
            except AlignmentError as error:
                for item in groups:
                    sources[item.id].append(
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
                    excluded[item.id].append(
                        {"source_image": source_path.name, "reason": error.reason}
                    )
                if on_progress is not None:
                    on_progress(index, len(images))
                continue
            for item in groups:
                splits: list[PreparedSplit] = []
                for crop in config.part.ranges_for(item):
                    if (source_path.name, crop.id) in blacklist:
                        excluded[item.id].append(
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
                        config.image_resize,
                        source_image=source_path.name,
                    )
                    filename = f"{source_path.stem}_{crop.id:02d}{source_path.suffix}"
                    write_image(targets[item.id] / filename, split)
                    splits.append(
                        PreparedSplit(
                            source_image=source_path.name,
                            split_id=crop.id,
                            image=filename,
                        )
                    )
                sources[item.id].append(
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
            if on_progress is not None:
                on_progress(index, len(images))
        for item in groups:
            manifest = PreparationManifest(
                model=config.model,
                group=item.id,
                range_ids=item.range_ids,
                preparation_fingerprint=preparation_fingerprint(config, group=item),
                created_at=datetime.now(UTC),
                sources=sources[item.id],
                excluded=excluded[item.id],
            )
            manifest.write_json(targets[item.id] / "manifest.json")
            manifests[item.id] = manifest

    _atomic_replace_directory(paths.prepared_train(config.model, group), populate)
    if not manifests:
        raise RuntimeError("training manifest was not created")
    return manifests


def prepare_testing(
    config: AppConfig,
    paths: ProjectPaths,
    *,
    aligner: Callable[..., AlignedImage] = align_orb,
    on_progress: ProgressCallback | None = None,
) -> PreparationManifest:
    source_dir = paths.original_test(config.model)
    images = list_images(source_dir)
    if on_progress is not None:
        on_progress(0, len(images))
    reference = resize_image(
        read_image(paths.original_train(config.model) / config.part.base),
        config.image_resize,
    )
    manifest: PreparationManifest | None = None

    def populate(stage: Path) -> None:
        nonlocal manifest
        sources: list[PreparedSource] = []
        for source_path in images:
            source = resize_image(read_image(source_path), config.image_resize)
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
                if on_progress is not None:
                    on_progress(len(sources), len(images))
                continue
            splits: list[PreparedSplit] = []
            for crop in config.part.ranges:
                split = _prepared_crop(
                    aligned.image,
                    crop,
                    config.image_size,
                    config.image_resize,
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
            if on_progress is not None:
                on_progress(len(sources), len(images))
        manifest = PreparationManifest(
            model=config.model,
            preparation_fingerprint=preparation_fingerprint(config),
            created_at=datetime.now(UTC),
            sources=sources,
        )
        manifest.write_json(stage / "manifest.json")

    _atomic_replace_directory(paths.prepared_test(config.model), populate)
    if manifest is None:  # pragma: no cover
        raise RuntimeError("testing manifest was not created")
    return manifest
