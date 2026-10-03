from typing import Any, cast

from app.runtime import DeviceSelection, RunRecorder


def test_workflow_records_runtime_contract() -> None:
    metadata = cast(
        dict[str, Any],
        RunRecorder(
            "test", "XX", DeviceSelection("cuda", "Smoke GPU", "CUDA is available")
        ).finish(0),
    )
    assert metadata["status"] == "success"
    assert metadata["duration_seconds"] >= 0
    assert metadata["started_at"]
    assert metadata["ended_at"]
    assert metadata["platform"]["python"]
    assert metadata["dependencies"]["anomalib"] == "2.6.2"


def test_workflow_completes_with_cpu_fallback() -> None:
    metadata = cast(
        dict[str, Any],
        RunRecorder(
            "train",
            "XX",
            DeviceSelection("cpu", "CPU", "CUDA is unavailable"),
        ).finish(0),
    )
    assert metadata["exit_code"] == 0
    assert metadata["device"]["type"] == "cpu"
    assert metadata["device"]["reason"] == "CUDA is unavailable"
