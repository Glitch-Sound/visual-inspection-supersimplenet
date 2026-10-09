from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import typer
from conftest import build_project
from filelock import FileLock

from app.common.artifact_transaction import _transaction_path
from app.common.cli import _run
from app.common.runtime import select_device


def test_group_req_024_s01(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = build_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    lock_path = paths.model_lock("XX")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    called = []
    with FileLock(lock_path), pytest.raises(typer.Exit) as error:
        _run("check", "XX", lambda *_args: called.append("ran"))
    assert error.value.exit_code == 3
    assert not called


def test_group_req_024_s02(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = build_project(tmp_path)
    shutil.copy2(paths.model_config("XX"), paths.model_config("YY"))
    monkeypatch.chdir(tmp_path)
    lock_path = paths.model_lock("XX")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    called = []
    with FileLock(lock_path):
        _run("check", "YY", lambda *_args: called.append("YY"))
    assert called == ["YY"]


def test_group_req_024_s03(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = build_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    targets = {
        "checkpoint": paths.checkpoint("XX", 0),
        "config": paths.model_config("XX"),
        "best_trial": paths.study_dir("XX", 0) / "best_trial.json",
    }
    for name, target in targets.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        if name != "config":
            target.write_text(f"old {name}")
        shutil.copy2(target, _transaction_path(target, "backup"))
    journal = paths.study_dir("XX", 0) / ".artifact-transaction.json"
    journal.write_text(
        json.dumps({"version": 1, "existed": {key: True for key in targets}})
    )
    targets["checkpoint"].write_text("partial new")
    observed = []
    _run(
        "check", "XX", lambda *_args: observed.append(targets["checkpoint"].read_text())
    )
    assert observed == ["old checkpoint"]
    assert not journal.exists()


def test_select_device_falls_back_to_cpu() -> None:
    assert (
        select_device(cuda_available=lambda: False, cuda_name=lambda: "unused").device
        == "cpu"
    )


def test_req_009_s01(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, paths = build_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "app.common.cli.select_device",
        lambda: select_device(
            cuda_available=lambda: True, cuda_name=lambda: "Test GPU"
        ),
    )
    seen = []
    _run(
        "test",
        "XX",
        lambda _paths, run: seen.append(run.device.device),
        needs_device=True,
    )
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert seen == ["cuda"]
    assert "使用デバイス: cuda" in captured.err
    assert result["device"]["type"] == "cuda"


def test_req_009_s02(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    build_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "app.common.cli.select_device",
        lambda: select_device(cuda_available=lambda: False, cuda_name=lambda: "unused"),
    )
    seen = []
    _run(
        "train",
        "XX",
        lambda _paths, run: seen.append(run.device.device),
        needs_device=True,
    )
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert seen == ["cpu"]
    assert "使用デバイス: cpu" in captured.err
    assert result["device"]["type"] == "cpu"
    assert result["device"]["reason"]


@pytest.mark.parametrize("command", ["check", "train-pre", "train", "test-pre", "test"])
def test_nreq_002_s01(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    import torch
    from group_evaluation_helpers import FakePredictor, aligned, project

    from app.common.runtime import DeviceSelection
    from app.image_preparation import cli as preparation_cli
    from app.image_preparation import preparation
    from app.model_evaluation import cli as evaluation_cli
    from app.model_training import cli as training_cli
    from app.model_training.search import TrialOutcome

    config, paths = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "app.common.cli.select_device", lambda: DeviceSelection("cpu", "CPU", "test")
    )
    monkeypatch.setattr(
        evaluation_cli,
        "CheckpointPredictor",
        lambda *_args, **_kwargs: FakePredictor(score=0.5),
    )
    monkeypatch.setattr(
        preparation_cli,
        "prepare_training",
        lambda config, paths, **kwargs: preparation.prepare_training(
            config, paths, aligner=aligned, **kwargs
        ),
    )
    monkeypatch.setattr(
        preparation_cli,
        "prepare_testing",
        lambda config, paths, **kwargs: preparation.prepare_testing(
            config, paths, aligner=aligned, **kwargs
        ),
    )
    if command == "train":
        preparation.prepare_training(config, paths, aligner=aligned)
        payload = json.loads(paths.model_config("XX").read_text())
        payload["groups"][0]["optuna_settings"]["execution"]["trials"] = 1
        paths.model_config("XX").write_text(json.dumps(payload))

        class FakeRunner:
            def __init__(self, directory, _device, _group):
                self.directory = directory

            def __call__(self, _parameters, _split, trial):
                self.directory.mkdir(parents=True, exist_ok=True)
                checkpoint = self.directory / f"trial_{trial.number}.ckpt"
                torch.save({"state_dict": {}}, checkpoint)
                return TrialOutcome([0.2], [0.1, 0.2], checkpoint)

        monkeypatch.setattr(training_cli, "AnomalibTrialRunner", FakeRunner)
    commands = {
        "check": lambda: preparation_cli._check_command(model="XX"),
        "train-pre": lambda: preparation_cli._train_pre_command(model="XX", group=None),
        "train": lambda: training_cli._train_command(model="XX", group=0, restart=True),
        "test-pre": lambda: preparation_cli._test_pre_command(model="XX"),
        "test": lambda: evaluation_cli._test_command(model="XX", group=0),
    }
    capsys.readouterr()
    commands[command]()
    captured = capsys.readouterr()
    assert f"開始: {command} 型番=XX" in captured.err
    assert "設定読込" in captured.err
    assert f"終了: {command} 成功" in captured.err
    assert json.loads(captured.out)["exit_code"] == 0
    assert json.loads(captured.out)["command"] == command
    assert len(captured.out.splitlines()) == 1


def test_nreq_002_s02(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    build_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    def warned(_paths, run):
        run.warnings.append("alignment failed")
        run.errors.append("split failed")
        return "partial"

    _run("test", "XX", warned)
    captured = capsys.readouterr()
    assert "警告: alignment failed" in captured.err
    assert "エラー: split failed" in captured.err
    assert json.loads(captured.out)["exit_code"] == 0

    def failed(_paths, _run):
        raise RuntimeError("cannot inspect")

    with pytest.raises(typer.Exit) as error:
        _run("test", "XX", failed)
    captured = capsys.readouterr()
    assert error.value.exit_code == 3
    assert "処理失敗: cannot inspect" in captured.err
    assert json.loads(captured.out)["exit_code"] == 3
