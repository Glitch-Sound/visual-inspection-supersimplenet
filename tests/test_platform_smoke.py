import runpy
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import torch
from conftest import build_project, write_test_image

from app.common.contracts import (
    AlignmentResult,
    BestTrialResult,
    InspectionResult,
    PreparationManifest,
    PreparedSource,
    PreparedSplit,
    ResultStatus,
    ScoreContract,
    SplitResult,
    TrialParametersContract,
)
from app.common.runtime import DeviceSelection, RunRecorder

SCRIPT = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "run_visual_inspection_smoke.py")
)
COMMANDS = cast(list[str], SCRIPT["COMMANDS"])
inspect_artifacts = cast(
    Callable[[Path, str], list[dict[str, Any]]], SCRIPT["inspect_artifacts"]
)


def test_workflow_records_runtime_contract(tmp_path: Path) -> None:
    metadata = RunRecorder(
        "test", "XX", DeviceSelection("cuda", "Smoke GPU", "CUDA is available")
    ).finish(0)
    assert metadata.status == "success"
    assert metadata.duration_seconds >= 0
    assert metadata.started_at
    assert metadata.ended_at
    assert metadata.platform.python
    assert metadata.dependencies["anomalib"] == "2.6.2"
    assert COMMANDS == ["check", "train-pre", "train", "test-pre", "test"]

    _config, paths = build_project(tmp_path)
    write_test_image(paths.check_image("XX"))
    for prepared in (paths.prepared_train("XX"), paths.prepared_test("XX")):
        split_path = prepared / "source_00.png"
        write_test_image(split_path)
        PreparationManifest(
            model="XX",
            created_at=datetime.now(UTC),
            sources=[
                PreparedSource(
                    source_image="source.png",
                    alignment=AlignmentResult(status="aligned"),
                    splits=[
                        PreparedSplit(
                            source_image="source.png",
                            split_id=0,
                            image=split_path.name,
                        )
                    ],
                )
            ],
        ).write_json(prepared / "manifest.json")

    checkpoint = paths.checkpoint("XX")
    checkpoint.parent.mkdir(parents=True)
    torch.save(
        {
            "visual_inspection": {
                "model": "XX",
                "score_source": "supersimplenet.pred_score",
                "anomalib_post_processor": False,
                "threshold": 0.5,
            }
        },
        checkpoint,
    )
    BestTrialResult(
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
        train_sources=["train.png"],
        validation_sources=["validation.png"],
        seed=42,
        dependencies={},
    ).write_json(paths.study_dir("XX") / "best_trial.json")

    result_dir = paths.results("XX")
    result_image = result_dir / "source_00.png_result.png"
    write_test_image(result_image)
    InspectionResult(
        source_image="source.png",
        model="XX",
        checkpoint="weights/XX.ckpt",
        score_contract=ScoreContract(),
        threshold=0.5,
        splits=[
            SplitResult(
                split_id=0,
                image="source_00.png",
                score=0.1,
                status=ResultStatus.NORMAL,
                result_image=result_image.name,
            )
        ],
        overall_status=ResultStatus.NORMAL,
        processed_at=datetime.now(UTC),
        alignment=AlignmentResult(status="aligned"),
        runtime=metadata,
    ).write_json(result_dir / "source.png.json")

    artifacts = inspect_artifacts(tmp_path, "XX")
    assert {artifact["name"] for artifact in artifacts} == {
        "check_image",
        "train_manifest",
        "checkpoint",
        "best_trial",
        "test_manifest",
        "results",
    }
    assert all(artifact["readable"] for artifact in artifacts)


def test_workflow_completes_with_cpu_fallback() -> None:
    metadata = RunRecorder(
        "train",
        "XX",
        DeviceSelection("cpu", "CPU", "CUDA is unavailable"),
    ).finish(0)
    assert metadata.exit_code == 0
    assert metadata.device.type == "cpu"
    assert metadata.device.reason == "CUDA is unavailable"
