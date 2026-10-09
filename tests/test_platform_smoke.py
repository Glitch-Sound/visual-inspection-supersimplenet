from __future__ import annotations

import runpy
from pathlib import Path

from group_evaluation_helpers import FakePredictor, aligned, project, recorder

from app.common.runtime import DeviceSelection, RunRecorder
from app.image_preparation.preparation import create_check_image, prepare_training
from app.model_evaluation import cli as evaluation_cli
from app.model_evaluation.cli import _test_command

SCRIPT = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "run_visual_inspection_smoke.py")
)
inspect_artifacts = SCRIPT["inspect_artifacts"]


def test_workflow_records_runtime_contract(tmp_path: Path, monkeypatch) -> None:
    config, paths = project(tmp_path, two=True)
    create_check_image(config, paths)
    prepare_training(config, paths, aligner=aligned)
    run = recorder()
    monkeypatch.setattr(
        evaluation_cli, "_run", lambda _cmd, _model, action, **_kw: action(paths, run)
    )
    monkeypatch.setattr(evaluation_cli, "CheckpointPredictor", FakePredictor)
    _test_command(model="XX", group=None)
    artifacts = inspect_artifacts(tmp_path, "XX")
    assert artifacts
    assert all(item["readable"] for item in artifacts)
    assert run.finish(0).groups == [0, 1]


def test_workflow_completes_with_cpu_fallback() -> None:
    metadata = RunRecorder(
        "train", "XX", DeviceSelection("cpu", "CPU", "CUDA is unavailable")
    ).finish(0)
    assert metadata.device.type == "cpu"
    assert metadata.exit_code == 0
