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
