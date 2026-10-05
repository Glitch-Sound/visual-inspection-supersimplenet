"""Inspection result aggregation and persistence."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from app.common.contracts import InspectionResult, ResultStatus, SplitResult


def aggregate_status(
    splits: Iterable[SplitResult], *, required_split_ids: set[int]
) -> tuple[ResultStatus, str | None]:
    items = list(splits)
    if any(item.status == ResultStatus.ANOMALY for item in items):
        return ResultStatus.ANOMALY, None
    observed = {item.split_id for item in items}
    statuses = {item.status for item in items}
    if observed == required_split_ids and statuses == {ResultStatus.NORMAL}:
        return ResultStatus.NORMAL, None
    return (
        ResultStatus.UNDETERMINED,
        "再撮影が必要です。別の扱いは評価者が判断してください。",
    )


def write_inspection_result(result: InspectionResult, path: Path) -> None:
    """Write a complete result atomically."""

    result.write_json(path)
