from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts import (
    AlignmentResult,
    InspectionResult,
    PreparationManifest,
    ResultStatus,
    ScoreContract,
    SplitResult,
)
from app.results import aggregate_status
from app.runtime import DeviceSelection, RunRecorder


def split(
    split_id: int, status: ResultStatus, score: float | None = None
) -> SplitResult:
    return SplitResult(
        split_id=split_id,
        image=f"split-{split_id}.png",
        score=score,
        status=status,
    )


def test_aggregate_prefers_anomaly() -> None:
    status, action = aggregate_status(
        [split(0, ResultStatus.ERROR), split(1, ResultStatus.ANOMALY, 0.9)],
        required_split_ids={0, 1},
    )
    assert status == ResultStatus.ANOMALY
    assert action is None


def test_aggregate_accepts_only_all_normal() -> None:
    status, action = aggregate_status(
        [split(0, ResultStatus.NORMAL, 0.1), split(1, ResultStatus.NORMAL, 0.2)],
        required_split_ids={0, 1},
    )
    assert status == ResultStatus.NORMAL
    assert action is None


def test_aggregate_marks_incomplete_result_undetermined() -> None:
    status, action = aggregate_status(
        [split(0, ResultStatus.NORMAL, 0.1), split(1, ResultStatus.ERROR)],
        required_split_ids={0, 1},
    )
    assert status == ResultStatus.UNDETERMINED
    assert action is not None and "再撮影" in action


def test_result_json_contains_traceable_contract(tmp_path: Path) -> None:
    runtime = RunRecorder(
        "test", "XX", DeviceSelection("cpu", "CPU", "CUDA is unavailable")
    ).finish(0)
    result = InspectionResult(
        source_image="source.png",
        model="XX",
        checkpoint="weights/XX.ckpt",
        score_contract=ScoreContract(),
        threshold=0.5,
        splits=[split(0, ResultStatus.ERROR)],
        overall_status=ResultStatus.UNDETERMINED,
        processed_at=datetime.now(UTC),
        alignment=AlignmentResult(status="undetermined", reason="homography_failed"),
        runtime=runtime,
        next_action="再撮影",
    )
    target = tmp_path / "result.json"
    result.write_json(target)
    restored = InspectionResult.read_json(target)
    assert restored == result
    assert restored.splits[0].score is None
    assert restored.score_contract.source == "supersimplenet.pred_score"
    assert restored.score_contract.anomalib_post_processor is False
    with pytest.raises(ValidationError):
        InspectionResult.model_validate(result.model_dump(exclude={"checkpoint"}))


def test_result_contract_rejects_invalid_score_and_runtime() -> None:
    runtime = RunRecorder(
        "test", "XX", DeviceSelection("cpu", "CPU", "CUDA is unavailable")
    ).finish(0)
    valid = InspectionResult(
        source_image="source.png",
        model="XX",
        checkpoint="weights/XX.ckpt",
        score_contract=ScoreContract(),
        threshold=0.5,
        splits=[split(0, ResultStatus.NORMAL, 0.1)],
        overall_status=ResultStatus.NORMAL,
        processed_at=datetime.now(UTC),
        alignment=AlignmentResult(status="aligned"),
        runtime=runtime,
    ).model_dump(mode="json")
    invalid_payloads: list[tuple[str, dict[str, object]]] = []

    wrong_source = deepcopy(valid)
    wrong_source["score_contract"]["source"] = "other.score"
    invalid_payloads.append(("score_contract.source", wrong_source))

    enabled_post_processor = deepcopy(valid)
    enabled_post_processor["score_contract"]["anomalib_post_processor"] = True
    invalid_payloads.append(
        ("score_contract.anomalib_post_processor", enabled_post_processor)
    )

    wrong_status = deepcopy(valid)
    wrong_status["splits"][0]["status"] = "unknown"
    invalid_payloads.append(("splits.0.status", wrong_status))

    wrong_alignment_status = deepcopy(valid)
    wrong_alignment_status["alignment"]["status"] = "unknown"
    invalid_payloads.append(("alignment.status", wrong_alignment_status))

    missing_runtime_field = deepcopy(valid)
    del missing_runtime_field["runtime"]["device"]
    invalid_payloads.append(("runtime.device", missing_runtime_field))

    naive_timestamp = deepcopy(valid)
    naive_timestamp["runtime"]["started_at"] = "2026-10-03T00:00:00"
    invalid_payloads.append(("runtime.started_at", naive_timestamp))

    for expected_location, payload in invalid_payloads:
        with pytest.raises(ValidationError) as captured:
            InspectionResult.model_validate(payload)
        assert expected_location in str(captured.value)


def test_manifest_contract_rejects_unsafe_or_inconsistent_entries(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"unchanged")
    base = {
        "model": "XX",
        "created_at": datetime.now(UTC).isoformat(),
        "sources": [
            {
                "source_image": "source.png",
                "alignment": {"status": "aligned"},
                "splits": [
                    {
                        "source_image": "source.png",
                        "split_id": 0,
                        "image": "source_00.png",
                    }
                ],
            }
        ],
        "excluded": [],
    }
    invalid: list[dict[str, object]] = []

    wrong_model = deepcopy(base)
    wrong_model["model"] = "../XX"
    invalid.append(wrong_model)

    unsafe_image = deepcopy(base)
    unsafe_image["sources"][0]["splits"][0]["image"] = "../../outside.png"
    invalid.append(unsafe_image)

    duplicate_source = deepcopy(base)
    duplicate_source["sources"].append(deepcopy(duplicate_source["sources"][0]))
    invalid.append(duplicate_source)

    parent_mismatch = deepcopy(base)
    parent_mismatch["sources"][0]["splits"][0]["source_image"] = "other.png"
    invalid.append(parent_mismatch)

    duplicate_split = deepcopy(base)
    duplicate_split["sources"][0]["splits"].append(
        {
            "source_image": "source.png",
            "split_id": 0,
            "image": "source_duplicate.png",
        }
    )
    invalid.append(duplicate_split)

    duplicate_split_image = deepcopy(base)
    duplicate_split_image["sources"].append(
        {
            "source_image": "other.png",
            "alignment": {"status": "aligned"},
            "splits": [
                {
                    "source_image": "other.png",
                    "split_id": 1,
                    "image": "source_00.png",
                }
            ],
        }
    )
    invalid.append(duplicate_split_image)

    for payload in invalid:
        with pytest.raises(ValidationError):
            PreparationManifest.model_validate(payload)
    assert outside.read_bytes() == b"unchanged"
