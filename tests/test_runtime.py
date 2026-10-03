import json
from pathlib import Path

import numpy as np
import pytest
import typer
from conftest import build_project, write_test_image

from app.cli import _run
from app.imaging import AlignedImage
from app.preparation import prepare_testing, prepare_training
from app.runtime import RunRecorder, select_device


def test_select_device_prefers_available_cuda() -> None:
    selected = select_device(lambda: True, lambda: "Test GPU")
    assert selected.device == "cuda"
    assert selected.name == "Test GPU"
    assert selected.reason == "CUDA is available"
    metadata = RunRecorder("train", "XX", selected).finish(0)
    assert metadata.device.type == "cuda"
    assert metadata.device.name == "Test GPU"
    assert metadata.device.reason == "CUDA is available"


def test_select_device_falls_back_to_cpu() -> None:
    selected = select_device(lambda: False, lambda: "unused")
    assert selected.device == "cpu"
    assert selected.reason == "CUDA is unavailable"

    def initialization_failure() -> bool:
        raise RuntimeError("driver initialization failed")

    failed = select_device(initialization_failure, lambda: "unused")
    assert failed.device == "cpu"
    assert failed.reason == "CUDA initialization failed: driver initialization failed"


@pytest.mark.parametrize("testing", [False, True])
def test_preparation_image_io_failure_is_processing_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    testing: bool,
) -> None:
    config, paths = build_project(tmp_path)
    write_test_image(paths.original_train("XX") / "base.png")
    source_dir = paths.original_test("XX") if testing else paths.original_train("XX")
    target = paths.prepared_test("XX") if testing else paths.prepared_train("XX")
    target.mkdir(parents=True)
    sentinel = target / "keep.txt"
    sentinel.write_text("old", encoding="utf-8")
    broken = source_dir / "broken.png"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_bytes(b"not an image")
    monkeypatch.chdir(tmp_path)

    def identity_aligner(image: np.ndarray, *_args: object) -> AlignedImage:
        return AlignedImage(image.copy(), matches=42, inlier_ratio=0.9)

    def action(_paths: object, _recorder: object) -> object:
        prepare = prepare_testing if testing else prepare_training
        return prepare(config, paths, aligner=identity_aligner)

    with pytest.raises(typer.Exit) as captured:
        _run("test-pre" if testing else "train-pre", "XX", action)

    output = json.loads(capsys.readouterr().out)
    assert captured.value.exit_code == 3
    assert output["exit_code"] == 3
    assert output["errors"] == ["image cannot be read: broken.png"]
    assert sentinel.read_text(encoding="utf-8") == "old"
