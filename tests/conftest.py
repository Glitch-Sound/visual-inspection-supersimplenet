from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.common.config import AppConfig, load_config
from app.common.paths import ProjectPaths

REPOSITORY_ROOT = Path(__file__).parents[1]


def build_project(
    root: Path,
    *,
    image_size: int = 8,
    ranges: list[dict[str, int]] | None = None,
    blacklist: list[dict[str, Any]] | None = None,
) -> tuple[AppConfig, ProjectPaths]:
    config_dir = root / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "setting.ini").write_text(
        f"[IMAGE]\nSIZE = {image_size}\n", encoding="utf-8"
    )
    payload = json.loads(
        (REPOSITORY_ROOT / "tests" / "fixtures" / "model_config.json").read_text(
            encoding="utf-8"
        )
    )
    payload["range"] = ranges or [{"id": 0, "x": 0, "y": 0}]
    payload["blacklist"] = blacklist or []
    (config_dir / "part_XX.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    paths = ProjectPaths(root)
    return load_config(root, "XX"), paths


def write_test_image(path: Path, *, size: int = 24, value: int = 80) -> np.ndarray:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = np.full((size, size, 3), value, dtype=np.uint8)
    cv2.circle(image, (size // 2, size // 2), max(1, size // 4), (200, 40, 120), -1)
    assert cv2.imwrite(str(path), image)
    return image
