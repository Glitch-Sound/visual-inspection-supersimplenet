from app.runtime import RunRecorder, select_device


def test_select_device_prefers_available_cuda() -> None:
    selected = select_device(lambda: True, lambda: "Test GPU")
    assert selected.device == "cuda"
    assert selected.name == "Test GPU"
    assert selected.reason == "CUDA is available"
    metadata = RunRecorder("train", "XX", selected).finish(0)
    assert metadata["device"] == {
        "type": "cuda",
        "name": "Test GPU",
        "reason": "CUDA is available",
    }


def test_select_device_falls_back_to_cpu() -> None:
    selected = select_device(lambda: False, lambda: "unused")
    assert selected.device == "cpu"
    assert selected.reason == "CUDA is unavailable"
