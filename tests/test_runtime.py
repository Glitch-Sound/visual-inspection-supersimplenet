import json
from pathlib import Path

import numpy as np
import pytest
import typer
from conftest import build_project, write_test_image

from app.common.cli import _run
from app.common.runtime import RunRecorder, select_device
from app.image_preparation.imaging import AlignedImage
from app.image_preparation.preparation import prepare_testing, prepare_training


def test_run_preserves_exit_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    def success(_paths: object, recorder: RunRecorder) -> str:
        recorder.warnings.append("warning")
        return "done"

    _run("check", "XX", success)
    output = json.loads(capsys.readouterr().out)
    assert output["exit_code"] == 0
    assert output["command"] == "check"
    assert output["model"] == "XX"
    assert output["result"] == "done"
    assert output["warnings"] == ["warning"]
    assert output["errors"] == []

    def invalid(_paths: object, _recorder: RunRecorder) -> None:
        raise ValueError("invalid input")

    with pytest.raises(typer.Exit) as input_error:
        _run("check", "XX", invalid)
    output = json.loads(capsys.readouterr().out)
    assert input_error.value.exit_code == 2
    assert output["exit_code"] == 2
    assert output["errors"] == ["invalid input"]
    assert "result" not in output

    def broken(_paths: object, _recorder: RunRecorder) -> None:
        raise RuntimeError("processing failed")

    with pytest.raises(typer.Exit) as processing_error:
        _run("check", "XX", broken)
    output = json.loads(capsys.readouterr().out)
    assert processing_error.value.exit_code == 3
    assert output["exit_code"] == 3
    assert output["errors"] == ["processing failed"]
    assert "result" not in output


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
