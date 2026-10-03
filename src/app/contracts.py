"""Machine-readable artifact contracts."""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(self.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    @classmethod
    def read_json(cls, path: Path):
        return cls.model_validate_json(path.read_text(encoding="utf-8"))


class ResultStatus(StrEnum):
    NORMAL = "normal"
    ANOMALY = "anomaly"
    UNDETERMINED = "undetermined"
    ERROR = "error"


class DeviceMetadata(ContractModel):
    type: Literal["cuda", "cpu"]
    name: str
    reason: str


class PlatformMetadata(ContractModel):
    system: str
    release: str
    machine: str
    python: str


class RunMetadata(ContractModel):
    command: str
    model: str
    started_at: datetime
    ended_at: datetime
    duration_seconds: float = Field(ge=0.0)
    exit_code: int
    status: Literal["success", "error"]
    device: DeviceMetadata
    platform: PlatformMetadata
    dependencies: dict[str, str]
    warnings: list[str]
    errors: list[str]

    @field_validator("started_at", "ended_at")
    @classmethod
    def timestamps_require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("run timestamps must include a timezone")
        return value


class AlignmentResult(ContractModel):
    status: str
    reason: str | None = None
    matches: int | None = None
    inlier_ratio: float | None = Field(default=None, ge=0.0, le=1.0)


class PreparedSplit(ContractModel):
    source_image: str
    split_id: int = Field(ge=0, le=99)
    image: str


class PreparedSource(ContractModel):
    source_image: str
    alignment: AlignmentResult
    splits: list[PreparedSplit] = Field(default_factory=list)


class PreparationManifest(ContractModel):
    model: str
    created_at: datetime
    sources: list[PreparedSource]
    excluded: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("created_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return value


class ScoreContract(ContractModel):
    source: str = "supersimplenet.pred_score"
    anomalib_post_processor: bool = False


class BestTrialResult(ContractModel):
    model: str
    trial_number: int = Field(ge=0)
    parameters: dict[str, Any]
    objective: float
    checkpoint: str
    score_contract: ScoreContract
    threshold: float = Field(ge=0.0, le=1.0)
    train_sources: list[str]
    validation_sources: list[str]
    seed: int
    dependencies: dict[str, str]


class SplitResult(ContractModel):
    split_id: int = Field(ge=0, le=99)
    image: str
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    status: ResultStatus
    result_image: str | None = None
    error: str | None = None

    @field_validator("score")
    @classmethod
    def validate_score(cls, value: float | None) -> float | None:
        return value


class InspectionResult(ContractModel):
    source_image: str
    model: str
    checkpoint: str
    score_contract: ScoreContract
    threshold: float = Field(ge=0.0, le=1.0)
    splits: list[SplitResult]
    overall_status: ResultStatus
    processed_at: datetime
    alignment: AlignmentResult
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    runtime: dict[str, Any]
    next_action: str | None = None

    @field_validator("processed_at")
    @classmethod
    def processed_at_requires_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("processed_at must include a timezone")
        return value


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
