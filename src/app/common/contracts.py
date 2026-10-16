"""Machine-readable artifact contracts."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from enum import StrEnum
from pathlib import Path, PureWindowsPath
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)

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
    groups: list[Annotated[StrictInt, Field(ge=0)]]
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

    @field_validator("groups")
    @classmethod
    def group_ids_are_unique(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("run groups must be unique")
        return value


class AlignmentResult(ContractModel):
    status: Literal["aligned", "failed", "undetermined"]
    reason: str | None = None
    recapture_required: bool = False
    matches: int | None = None
    inlier_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    inlier_reprojection_rmse_px: float | None = Field(
        default=None, ge=0.0, allow_inf_nan=False
    )


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
        source_path = Path(self.source_image)
        for split in self.splits:
            expected = f"{source_path.stem}_{split.split_id:02d}{source_path.suffix}"
            if split.image != expected:
                raise ValueError(
                    f"split image {split.image!r} does not match split_id "
                    f"{split.split_id}; expected {expected!r}"
                )
        split_ids = [split.split_id for split in self.splits]
        if len(split_ids) != len(set(split_ids)):
            raise ValueError("split_id must be unique within a source image")
        split_images = [split.image for split in self.splits]
        if len(split_images) != len(set(split_images)):
            raise ValueError("split image must be unique within a source image")
        return self


class PreparationManifest(ContractModel):
    model: str
    group: Annotated[StrictInt, Field(ge=0)] | None = None
    range_ids: list[Annotated[StrictInt, Field(ge=0, le=99)]] | None = None
    preparation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
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
        if self.group is None and self.range_ids is not None:
            raise ValueError("test manifest must not have range_ids")
        if self.group is not None and (
            not self.range_ids or len(self.range_ids) != len(set(self.range_ids))
        ):
            raise ValueError("train manifest range_ids must be nonempty and unique")
        source_images = [source.source_image for source in self.sources]
        if len(source_images) != len(set(source_images)):
            raise ValueError("source_image must be unique within a manifest")
        split_images = [
            split.image for source in self.sources for split in source.splits
        ]
        if len(split_images) != len(set(split_images)):
            raise ValueError("split image must be unique within a manifest")
        return self


def load_preparation_manifest(
    prepared_dir: Path,
    *,
    model: str,
    allowed_split_ids: set[int],
    group: int | None = None,
    fingerprint: str | None = None,
) -> PreparationManifest:
    """Validate a prepared input before training or inference reads any image."""

    if prepared_dir.is_symlink():
        raise ValueError(f"prepared directory must not be a symlink: {prepared_dir}")
    manifest_path = prepared_dir / "manifest.json"
    if manifest_path.is_symlink():
        raise ValueError(f"prepared manifest must not be a symlink: {manifest_path}")
    manifest = PreparationManifest.read_json(manifest_path)
    if manifest.model != model:
        raise ValueError(
            f"prepared manifest model mismatch: expected {model}, got {manifest.model}"
        )
    if manifest.group != group:
        raise ValueError(
            f"prepared manifest group mismatch: expected {group}, got {manifest.group}"
        )
    if group is not None and set(manifest.range_ids or []) != allowed_split_ids:
        raise ValueError("prepared manifest range_ids do not match group")
    if fingerprint is not None and manifest.preparation_fingerprint != fingerprint:
        raise ValueError(
            "prepared manifest fingerprint mismatch; rerun train-pre or test-pre"
        )
    for source in manifest.sources:
        for split in source.splits:
            if split.split_id not in allowed_split_ids:
                raise ValueError(
                    f"split_id {split.split_id} for {source.source_image} "
                    "is not configured"
                )
            image_path = prepared_dir / split.image
            if image_path.is_symlink():
                raise ValueError(
                    f"prepared split image must not be a symlink: {image_path}"
                )
    return manifest


class ScoreContract(ContractModel):
    source: Literal["supersimplenet.pred_score"] = "supersimplenet.pred_score"
    anomalib_post_processor: Literal[False] = False


class TrialParametersContract(ContractModel):
    learning_rate_multiplier: float = Field(gt=0.0)
    batch_size: int = Field(gt=0)
    epochs: int = Field(gt=0)
    feature_layers: list[Literal["layer2", "layer3"]] = Field(min_length=1)
    image_size: int = Field(gt=0)


class FoldRecord(ContractModel):
    train_sources: list[str] = Field(min_length=1)
    validation_sources: list[str] = Field(min_length=1)

    @field_validator("train_sources", "validation_sources")
    @classmethod
    def safe_sources(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("fold source names must be unique")
        return [_safe_filename(name) for name in value]

    @model_validator(mode="after")
    def disjoint_sources(self) -> FoldRecord:
        if set(self.train_sources) & set(self.validation_sources):
            raise ValueError("fold train and validation sources must be disjoint")
        return self


class SourceScore(ContractModel):
    source_image: str
    split_image: str
    score: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)

    @field_validator("source_image", "split_image")
    @classmethod
    def safe_image(cls, value: str) -> str:
        return _safe_filename(value)


class SplitThreshold(ContractModel):
    value: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    source: Literal["calculated", "group_fallback"]
    score_count: StrictInt = Field(ge=0)

    @field_validator("value", mode="before")
    @classmethod
    def finite_numeric_value(cls, value: object) -> object:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError("split threshold value must be a finite JSON number")
        return value


ThresholdSource = Literal[
    "split_calculated",
    "group_fallback",
    "manual_override",
    "group_calculated",
    "group_manual_override",
]


class BestTrialResult(ContractModel):
    model: str
    group: Annotated[StrictInt, Field(ge=0)]
    range_ids: list[Annotated[StrictInt, Field(ge=0, le=99)]] = Field(min_length=1)
    trial_number: int = Field(ge=0)
    parameters: TrialParametersContract
    objective: float
    objective_name: Literal["normal_percentile", "synthetic_auroc"] = (
        "normal_percentile"
    )
    normal_p99: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    synthetic_auroc: float | None = Field(
        default=None, ge=0.0, le=1.0, allow_inf_nan=False
    )
    synthetic_scores_summary: dict[str, float | int] | None = None
    synthetic_validation: dict[str, object] | None = None
    checkpoint: str
    threshold_score_model: Literal["final_checkpoint", "cross_validation"] | None = None
    threshold_model_checkpoint: str | None = None
    score_contract: ScoreContract
    threshold: float = Field(ge=0.0, le=1.0)
    threshold_method: Literal["training_percentile", "out_of_fold_percentile"] = (
        "training_percentile"
    )
    threshold_percentile: float | None = Field(default=None, gt=0.0, le=100.0)
    threshold_margin: float = Field(default=0.0, ge=0.0, le=1.0, allow_inf_nan=False)
    threshold_unit: Literal["group", "split"] = "group"
    min_score_count: StrictInt | None = Field(default=None, ge=1)
    split_thresholds: dict[str, SplitThreshold] = Field(default_factory=dict)
    threshold_warnings: list[str] = Field(default_factory=list)

    @field_validator("split_thresholds", mode="before")
    @classmethod
    def validate_split_keys(cls, value: object) -> object:
        if not isinstance(value, dict) or any(
            not isinstance(key, str) or not re.fullmatch(r"0|[1-9][0-9]*", key)
            for key in value
        ):
            raise ValueError("split_thresholds keys must be canonical split ids")
        return value

    cross_validation: list[FoldRecord] = Field(default_factory=list)
    score_by_source: list[SourceScore] = Field(default_factory=list)
    final_train_sources: list[str] = Field(default_factory=list)
    train_sources: list[str]
    validation_sources: list[str]
    seed: int
    dependencies: dict[str, str]

    @field_validator("model")
    @classmethod
    def model_is_safe(cls, value: str) -> str:
        return _safe_model(value)

    @field_validator("train_sources", "validation_sources", "final_train_sources")
    @classmethod
    def source_filenames_are_safe(cls, value: list[str]) -> list[str]:
        for filename in value:
            _safe_filename(filename)
        if len(value) != len(set(value)):
            raise ValueError("source image names must be unique")
        return value

    @model_validator(mode="after")
    def datasets_are_disjoint(self) -> BestTrialResult:
        if self.threshold_score_model is not None:
            expected = (
                "final_checkpoint"
                if self.threshold_method == "training_percentile"
                else "cross_validation"
            )
            if self.threshold_score_model != expected:
                raise ValueError("threshold score model does not match method")
            if expected == "final_checkpoint":
                if self.threshold_model_checkpoint != self.checkpoint:
                    raise ValueError(
                        "threshold model checkpoint does not match checkpoint"
                    )
            elif self.threshold_model_checkpoint is not None:
                raise ValueError("cross-validation threshold has no single checkpoint")
        elif self.threshold_model_checkpoint is not None:
            raise ValueError("threshold model checkpoint requires score model")
        if len(self.range_ids) != len(set(self.range_ids)):
            raise ValueError("best_trial range_ids must be unique")
        if self.threshold_unit == "split":
            if (
                self.min_score_count is None
                or self.threshold_method != "out_of_fold_percentile"
            ):
                raise ValueError(
                    "split threshold requires out_of_fold_percentile and min_score_count"
                )
            if set(self.split_thresholds) != {str(item) for item in self.range_ids}:
                raise ValueError("split thresholds must cover range_ids")
            for item in self.split_thresholds.values():
                if (
                    item.source == "calculated"
                    and item.score_count < self.min_score_count
                ):
                    raise ValueError(
                        "calculated split threshold has insufficient score_count"
                    )
                if (
                    item.source == "group_fallback"
                    and item.score_count >= self.min_score_count
                ):
                    raise ValueError(
                        "group fallback must have insufficient score_count"
                    )
                if item.source == "group_fallback" and not math.isclose(
                    item.value, self.threshold
                ):
                    raise ValueError("group fallback must match group threshold")
        elif self.min_score_count is not None or self.split_thresholds:
            raise ValueError("group threshold must not have split settings")
        if set(self.train_sources) & set(self.validation_sources):
            raise ValueError("train_sources and validation_sources must be disjoint")
        if self.threshold_method == "out_of_fold_percentile":
            if not self.cross_validation or not self.score_by_source:
                raise ValueError(
                    "out_of_fold_percentile requires fold and score records"
                )
            if self.threshold_percentile is None or not self.final_train_sources:
                raise ValueError(
                    "out_of_fold_percentile requires percentile and final sources"
                )
            source_names = {item.source_image for item in self.score_by_source}
            if source_names != set(self.final_train_sources):
                raise ValueError("out-of-fold scores must cover final training sources")
            validation = [
                name
                for fold in self.cross_validation
                for name in fold.validation_sources
            ]
            if sorted(validation) != sorted(self.final_train_sources):
                raise ValueError("folds must validate every final training source once")
            if len({item.split_image for item in self.score_by_source}) != len(
                self.score_by_source
            ):
                raise ValueError("out-of-fold split image names must be unique")
            for fold in self.cross_validation:
                if set(fold.train_sources) | set(fold.validation_sources) != set(
                    self.final_train_sources
                ):
                    raise ValueError("folds must cover all final training sources")
        return self


class SplitResult(ContractModel):
    split_id: int = Field(ge=0, le=99)
    image: str
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    status: ResultStatus
    result_image: str | None = None
    error: str | None = None
    threshold: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    threshold_source: ThresholdSource | None = None

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
    group: Annotated[StrictInt, Field(ge=0)]
    range_ids: list[Annotated[StrictInt, Field(ge=0, le=99)]] = Field(min_length=1)
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
        if len(self.range_ids) != len(set(self.range_ids)):
            raise ValueError("inspection range_ids must be unique")
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
