import io
import json
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import typer
from conftest import build_project, write_test_image

from app.common.cli import PreparationProgress, _run
from app.common.config import AppConfig
from app.common.contracts import (
    BestTrialResult,
    PreparationManifest,
    ScoreContract,
    TrialParametersContract,
)
from app.common.paths import ProjectPaths
from app.common.runtime import DeviceSelection, RunRecorder, select_device
from app.image_preparation.cli import (
    _check_command,
    _test_pre_command,
    _train_pre_command,
)
from app.image_preparation.imaging import AlignedImage
from app.image_preparation.preparation import (
    create_check_image,
    prepare_testing,
    prepare_training,
)
from app.model_evaluation.cli import _test_command
from app.model_training.cli import _train_command


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


def test_resize_zero_dimension_is_processing_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config, paths = build_project(tmp_path, image_size=1)
    config = config.model_copy(update={"image_resize": 0.1})
    write_test_image(paths.original_train("XX") / "base.png", size=1)
    target = paths.check_image("XX")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"previous check image")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(typer.Exit) as error:
        _run(
            "check",
            "XX",
            lambda _paths, _recorder: create_check_image(config, paths),
        )

    output = json.loads(capsys.readouterr().out)
    assert error.value.exit_code == 3
    assert output["exit_code"] == 3
    assert "IMAGE.RESIZE makes the image dimension zero" in output["errors"]
    assert target.read_bytes() == b"previous check image"


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


def test_change_nreq_002_01(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _config, paths = build_project(tmp_path)
    payload = json.loads(paths.model_config("XX").read_text())
    payload["optuna_settings"]["threshold"]["value"] = 0.5
    paths.model_config("XX").write_text(json.dumps(payload))
    write_test_image(paths.original_train("XX") / "base.png")
    write_test_image(paths.original_train("XX") / "normal.png")
    write_test_image(paths.original_test("XX") / "sample.png")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "app.common.cli.select_device",
        lambda: DeviceSelection("cpu", "CPU", "test"),
    )

    def aligner(image: np.ndarray, *_args: object) -> AlignedImage:
        return AlignedImage(image.copy(), matches=42, inlier_ratio=0.9)

    def training_preparation(
        config: AppConfig,
        output_paths: ProjectPaths,
        *,
        on_progress: Callable[[int, int], None],
    ) -> PreparationManifest:
        return prepare_training(
            config, output_paths, aligner=aligner, on_progress=on_progress
        )

    def testing_preparation(
        config: AppConfig,
        output_paths: ProjectPaths,
        *,
        on_progress: Callable[[int, int], None],
    ) -> PreparationManifest:
        return prepare_testing(
            config, output_paths, aligner=aligner, on_progress=on_progress
        )

    monkeypatch.setattr(
        "app.image_preparation.cli.prepare_training", training_preparation
    )
    monkeypatch.setattr(
        "app.image_preparation.cli.prepare_testing", testing_preparation
    )
    study = SimpleNamespace(trials=[object()])
    monkeypatch.setattr(
        "app.model_training.cli.split_by_source", lambda *_a, **_k: object()
    )
    monkeypatch.setattr("app.model_training.cli.create_study", lambda *_a: study)
    monkeypatch.setattr(
        "app.model_training.cli.AnomalibTrialRunner", lambda *_a: object()
    )
    monkeypatch.setattr("app.model_training.cli.run_search", lambda *_a: (study, {}))
    monkeypatch.setattr(
        "app.model_training.cli.persist_best_trial",
        lambda **_kwargs: SimpleNamespace(objective=0.1, threshold=0.5),
    )
    best = BestTrialResult(
        model="XX",
        trial_number=0,
        parameters=TrialParametersContract(
            learning_rate_multiplier=1.0,
            batch_size=4,
            epochs=200,
            feature_layers=["layer2"],
            image_size=256,
        ),
        objective=0.1,
        checkpoint="weights/XX.ckpt",
        score_contract=ScoreContract(),
        threshold=0.5,
        train_sources=["base.png"],
        validation_sources=["normal.png"],
        seed=42,
        dependencies={},
    )
    best.write_json(paths.study_dir("XX") / "best_trial.json")
    monkeypatch.setattr(
        "app.model_evaluation.cli.CheckpointPredictor", lambda *_a, **_k: object()
    )

    def evaluate_stub(
        _config: AppConfig,
        _paths: ProjectPaths,
        *,
        on_threshold_selected: Callable[[float], None],
        **_kwargs: object,
    ) -> list[object]:
        on_threshold_selected(0.5)
        return []

    monkeypatch.setattr("app.model_evaluation.cli.evaluate_model", evaluate_stub)

    for command, action, expected_stage in (
        ("check", lambda: _check_command("XX"), "確認画像保存"),
        ("train-pre", lambda: _train_pre_command("XX"), "学習準備完了"),
        ("train", lambda: _train_command("XX", restart=False), "学習完了"),
        ("test-pre", lambda: _test_pre_command("XX"), "試験準備完了"),
        ("test", lambda: _test_command("XX", restart=False), "判定閾値"),
    ):
        action()
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert captured.out.count("\n") == 1
        assert output["exit_code"] == 0
        assert f"開始: {command} 型番=XX" in captured.err
        assert expected_stage in captured.err
        assert f"終了: {command} 成功" in captured.err
        if command in {"train-pre", "test-pre"}:
            assert "準備進捗 0/" in captured.err
            assert "準備進捗" in captured.err
        if command == "test":
            assert captured.err.index("判定閾値") < captured.err.index("分割画像を推論")


def test_change_nreq_002_02(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    def warning(_paths: object, recorder: RunRecorder) -> None:
        recorder.warnings.append("sample.png: 位置合わせ失敗")

    _run("test-pre", "XX", warning)
    captured = capsys.readouterr()
    assert "警告: sample.png: 位置合わせ失敗" in captured.err
    assert json.loads(captured.out)["exit_code"] == 0

    def error(_paths: object, _recorder: RunRecorder) -> None:
        raise ValueError("inspection_threshold が不正")

    with pytest.raises(typer.Exit) as caught:
        _run("test", "XX", error)
    captured = capsys.readouterr()
    assert caught.value.exit_code == 2
    assert "入力不備: inspection_threshold が不正" in captured.err
    assert json.loads(captured.out)["errors"] == ["inspection_threshold が不正"]

    def partial_error(_paths: object, recorder: RunRecorder) -> str:
        recorder.errors.append("sample.png: split 0: 推論失敗")
        return "1 source images"

    _run("test", "XX", partial_error)
    captured = capsys.readouterr()
    assert "エラー: sample.png: split 0: 推論失敗" in captured.err
    assert "終了: test 処理完了・一部エラー=1" in captured.err
    assert json.loads(captured.out)["exit_code"] == 0


def test_train_pre_summary_counts_blacklisted_splits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _config, paths = build_project(
        tmp_path, blacklist=[{"image": "base.png", "id": [0]}]
    )
    write_test_image(paths.original_train("XX") / "base.png")
    monkeypatch.chdir(tmp_path)

    def prepare(
        config: AppConfig,
        output_paths: ProjectPaths,
        *,
        on_progress: Callable[[int, int], None],
    ) -> PreparationManifest:
        return prepare_training(
            config,
            output_paths,
            aligner=lambda image, *_args: AlignedImage(
                image.copy(), matches=42, inlier_ratio=0.9
            ),
            on_progress=on_progress,
        )

    monkeypatch.setattr("app.image_preparation.cli.prepare_training", prepare)
    _train_pre_command("XX")
    output = capsys.readouterr()
    assert "対象=1 準備=0 除外元画像=1 ブラックリスト除外分割=1" in output.err
    assert json.loads(output.out)["exit_code"] == 0


def test_preparation_progress_uses_bar_on_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TerminalBuffer(io.StringIO):
        def isatty(self) -> bool:
            return True

    buffer = TerminalBuffer()
    monkeypatch.setattr(sys, "stderr", buffer)
    with PreparationProgress() as progress:
        progress.update(0, 1)
        progress.update(1, 1)
    output = buffer.getvalue()
    assert "準備進捗" in output
    assert "1/1" in output
