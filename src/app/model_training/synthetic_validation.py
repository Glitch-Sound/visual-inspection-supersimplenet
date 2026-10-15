"""Deterministic validation-only synthetic defects."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from app.common.config import SyntheticValidationSettings


def _image_seed(seed: int, group: int, name: str) -> int:
    digest = hashlib.sha256(f"{seed}:{group}:{name}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def synthesize_image(
    source: Path,
    *,
    group: int,
    settings: SyntheticValidationSettings,
) -> Image.Image:
    """Return a changed RGB copy, leaving the prepared image untouched."""
    with Image.open(source) as opened:
        original = opened.convert("RGB")
    width, height = original.size
    if min(width, height) < 1:
        raise ValueError(f"synthetic validation image is empty: {source.name}")
    rng = np.random.default_rng(_image_seed(settings.seed, group, source.name))
    defect = settings.types[int(rng.integers(len(settings.types)))]
    strength = settings.intensity
    image = original.copy()
    draw = ImageDraw.Draw(image)
    cx = int(rng.integers(1, width - 1)) if width > 2 else int(rng.integers(width))
    cy = int(rng.integers(1, height - 1)) if height > 2 else int(rng.integers(height))
    radius = max(1, round(min(width, height) * (0.02 + 0.1 * strength)))
    base = np.asarray(original, dtype=np.uint8)
    pixel = base[cy, cx]
    target = 255 if float(np.mean(pixel)) < 128 else 0

    # Preserve a one-level difference when a small intensity rounds to zero.
    def blended_channel(channel: np.uint8) -> int:
        original_channel = int(channel)
        blended = round((1 - strength) * original_channel + strength * target)
        if blended == original_channel:
            return original_channel + (1 if target > original_channel else -1)
        return blended

    color = tuple(blended_channel(channel) for channel in pixel)
    if defect == "scratch":
        length = max(2, round(min(width, height) * (0.12 + 0.38 * strength)))
        draw.line(
            (max(0, cx - length // 2), cy, min(width - 1, cx + length // 2), cy),
            fill=color,
            width=max(1, round(1 + 4 * strength)),
        )
    elif defect == "stain":
        overlay = Image.new("RGB", image.size)
        mask = Image.new("L", image.size)
        ImageDraw.Draw(mask).ellipse(
            (cx - radius, cy - radius, cx + radius, cy + radius), fill=255
        )
        mask = mask.filter(ImageFilter.GaussianBlur(max(0.5, radius * 0.45)))
        overlay.paste(color, (0, 0, width, height))
        image.paste(overlay, (0, 0), mask)
    elif defect == "spot":
        for _ in range(max(1, round(2 + 8 * strength))):
            x = int(np.clip(cx + rng.integers(-radius, radius + 1), 0, width - 1))
            y = int(np.clip(cy + rng.integers(-radius, radius + 1), 0, height - 1))
            draw.ellipse((x, y, x + radius, y + radius), fill=color)
    else:
        side = max(1, round(min(width, height) * (0.04 + 0.18 * strength)))
        draw.rectangle(
            (cx, cy, min(width - 1, cx + side), min(height - 1, cy + side)),
            fill=color,
        )
    if np.array_equal(np.asarray(original), np.asarray(image)):
        image.putpixel((cx, cy), color)
    return image


def create_synthetic_validation(
    images: Sequence[Path],
    destination: Path,
    *,
    group: int,
    settings: SyntheticValidationSettings,
) -> tuple[Path, ...]:
    destination.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for index, source in enumerate(images):
        target = destination / f"{index:06d}_{source.stem}.png"
        synthesize_image(source, group=group, settings=settings).save(target)
        outputs.append(target)
    return tuple(outputs)
