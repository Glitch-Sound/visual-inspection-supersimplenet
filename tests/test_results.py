from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts import (
    AlignmentResult,
    InspectionResult,
    ResultStatus,
    ScoreContract,
    SplitResult,
)
from app.results import aggregate_status


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
        runtime={"device": {"type": "cpu"}, "duration_seconds": 1.0},
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
