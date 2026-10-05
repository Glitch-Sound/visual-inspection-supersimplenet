"""Shared image input and output."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

ImageArray = NDArray[np.uint8]


class ImageReadError(RuntimeError):
    """Raised when an expected image cannot be decoded."""


def read_image(path: Path) -> ImageArray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ImageReadError(f"image cannot be read: {path.name}")
    return cast(ImageArray, image)


def write_image(path: Path, image: ImageArray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), image):
        raise OSError(f"image write failed: {path.name}")
