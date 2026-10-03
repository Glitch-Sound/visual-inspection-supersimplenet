from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import build_project, write_test_image
from pydantic import ValidationError

from app.config import load_config, load_image_size
from app.paths import ProjectPaths
from app.preparation import create_check_image


@pytest.mark.parametrize("value", ["10.5", "0", "-1", "500 # comment"])
def test_check_rejects_invalid_ranges(tmp_path: Path, value: str) -> None:
    config, paths = build_project(tmp_path)
    paths.global_config.write_text(f"[IMAGE]\nSIZE = {value}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="IMAGE.SIZE"):
        load_image_size(paths.global_config)

    paths.global_config.write_text("[IMAGE]\nSIZE = 8\n", encoding="utf-8")
    payload = json.loads(paths.model_config("XX").read_text(encoding="utf-8"))
    payload["range"].append(payload["range"][0])
    paths.model_config("XX").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValidationError, match="range.id"):
        load_config(tmp_path, "XX")

    with pytest.raises(ValueError, match="model must match"):
        ProjectPaths(tmp_path).model_config("../XX")

    write_test_image(paths.original_train("XX") / "base.png")
    create_check_image(config, paths)
    existing = paths.check_image("XX").read_bytes()
    invalid = config.model_copy(
        update={
            "part": config.part.model_copy(
                update={"ranges": [config.part.ranges[0].model_copy(update={"x": 99})]}
            )
        }
    )
    with pytest.raises(ValueError, match="outside image bounds"):
        create_check_image(invalid, paths)
    assert paths.check_image("XX").read_bytes() == existing
