"""Machine-readable artifact contracts."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from enum import StrEnum
from pathlib import Path, PureWindowsPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MODEL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def _safe_filename(value: str) -> str:
    if (
        not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or Path(value).is_absolute()
        or PureWindowsPath(value).drive
    ):
        raise ValueError("must be a filename without path components")
    return value


def _safe_model(value: str) -> str:
    if not MODEL_NAME_PATTERN.fullmatch(value):
        raise ValueError("must match ^[A-Za-z0-9][A-Za-z0-9_-]*$")
    return value


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        try:
            temporary.write_text(
                self.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
            temporary.replace(path)
        finally:
            if temporary.exists():
                temporary.unlink()

    @classmethod
    def read_json(cls, path: Path):
        return cls.model_validate_json(path.read_text(encoding="utf-8"))


class HeatmapRange(ContractModel):
    min: float
    max: float

    @field_validator("min", "max", mode="before")
    @classmethod
    def finite_number(cls, value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("heatmap_range bounds must be finite JSON numbers")
        try:
            finite = math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            raise ValueError("heatmap_range bounds must be finite JSON numbers")
        return value

    @model_validator(mode="after")
    def ordered_bounds(self) -> HeatmapRange:
        if self.min >= self.max:
            raise ValueError("heatmap_range.min must be less than max")
        return self


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
    status: Literal["aligned", "failed", "undetermined"]
    reason: str | None = None
    matches: int | None = None
    inlier_ratio: float | None = Field(default=None, ge=0.0, le=1.0)


class PreparedSplit(ContractModel):
    source_image: str
    split_id: int = Field(ge=0, le=99)
    image: str

    @field_validator("source_image", "image")
    @classmethod
    def filenames_are_safe(cls, value: str) -> str:
        return _safe_filename(value)


class PreparedSource(ContractModel):
    source_image: str
    alignment: AlignmentResult
    splits: list[PreparedSplit] = Field(default_factory=list)

    @field_validator("source_image")
    @classmethod
    def source_filename_is_safe(cls, value: str) -> str:
        return _safe_filename(value)

    @model_validator(mode="after")
    def splits_match_source(self) -> PreparedSource:
        if any(split.source_image != self.source_image for split in self.splits):
            raise ValueError("split source_image must match parent source_image")
        split_ids = [split.split_id for split in self.splits]
        if len(split_ids) != len(set(split_ids)):
            raise ValueError("split_id must be unique within a source image")
        split_images = [split.image for split in self.splits]
        if len(split_images) != len(set(split_images)):
            raise ValueError("split image must be unique within a source image")
        return self


class PreparationManifest(ContractModel):
    model: str
    created_at: datetime
    sources: list[PreparedSource]
    excluded: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("model")
    @classmethod
    def model_is_safe(cls, value: str) -> str:
        return _safe_model(value)

    @field_validator("created_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return value

    @model_validator(mode="after")
    def source_images_are_unique(self) -> PreparationManifest:
        source_images = [source.source_image for source in self.sources]
        if len(source_images) != len(set(source_images)):
            raise ValueError("source_image must be unique within a manifest")
        split_images = [
            split.image for source in self.sources for split in source.splits
        ]
        if len(split_images) != len(set(split_images)):
            raise ValueError("split image must be unique within a manifest")
        return self


class ScoreContract(ContractModel):
    source: Literal["supersimplenet.pred_score"] = "supersimplenet.pred_score"
    anomalib_post_processor: Literal[False] = False


class TrialParametersContract(ContractModel):
    learning_rate_multiplier: float = Field(gt=0.0)
    batch_size: int = Field(gt=0)
    epochs: int = Field(gt=0)
    feature_layers: list[Literal["layer2", "layer3"]] = Field(min_length=1)
    image_size: int = Field(gt=0)


class BestTrialResult(ContractModel):
    model: str
    trial_number: int = Field(ge=0)
    parameters: TrialParametersContract
    objective: float
    checkpoint: str
    score_contract: ScoreContract
    threshold: float = Field(ge=0.0, le=1.0)
    train_sources: list[str]
    validation_sources: list[str]
    seed: int
    dependencies: dict[str, str]

    @field_validator("model")
    @classmethod
    def model_is_safe(cls, value: str) -> str:
        return _safe_model(value)

    @field_validator("train_sources", "validation_sources")
    @classmethod
    def source_filenames_are_safe(cls, value: list[str]) -> list[str]:
        for filename in value:
            _safe_filename(filename)
        if len(value) != len(set(value)):
            raise ValueError("source image names must be unique")
        return value

    @model_validator(mode="after")
    def datasets_are_disjoint(self) -> BestTrialResult:
        if set(self.train_sources) & set(self.validation_sources):
            raise ValueError("train_sources and validation_sources must be disjoint")
        return self


class SplitResult(ContractModel):
    split_id: int = Field(ge=0, le=99)
    image: str
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    status: ResultStatus
    result_image: str | None = None
    error: str | None = None

    @field_validator("image")
    @classmethod
    def image_filename_is_safe(cls, value: str) -> str:
        return _safe_filename(value)

    @field_validator("result_image")
    @classmethod
    def result_filename_is_safe(cls, value: str | None) -> str | None:
        return None if value is None else _safe_filename(value)

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
    heatmap_range: HeatmapRange
    splits: list[SplitResult]
    overall_status: ResultStatus
    processed_at: datetime
    alignment: AlignmentResult
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    runtime: RunMetadata
    next_action: str | None = None

    @field_validator("source_image")
    @classmethod
    def source_filename_is_safe(cls, value: str) -> str:
        return _safe_filename(value)

    @field_validator("model")
    @classmethod
    def model_is_safe(cls, value: str) -> str:
        return _safe_model(value)

    @field_validator("processed_at")
    @classmethod
    def processed_at_requires_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("processed_at must include a timezone")
        return value

    @model_validator(mode="after")
    def split_identifiers_are_unique(self) -> InspectionResult:
        split_ids = [split.split_id for split in self.splits]
        if len(split_ids) != len(set(split_ids)):
            raise ValueError("split_id must be unique within an inspection result")
        result_images = [
            split.result_image
            for split in self.splits
            if split.result_image is not None
        ]
        if len(result_images) != len(set(result_images)):
            raise ValueError("result_image must be unique within an inspection result")
        if self.runtime.model != self.model:
            raise ValueError("runtime.model must match inspection model")
        return self


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
