"""Typed configuration loading and cross-field validation."""

from __future__ import annotations

import configparser
import hashlib
import json
import math
import re
import warnings
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    ValidationError,
    field_validator,
    model_validator,
)

from app.common.contracts import HeatmapRange
from app.common.paths import ProjectPaths, validate_model_name

Probability = Annotated[float, Field(ge=0.0, le=1.0)]
PositiveFloat = Annotated[float, Field(gt=0.0)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CropRange(StrictModel):
    id: Annotated[StrictInt, Field(ge=0, le=99)]
    x: Annotated[StrictInt, Field(ge=0)]
    y: Annotated[StrictInt, Field(ge=0)]


class BlacklistEntry(StrictModel):
    image: str
    id: list[Annotated[StrictInt, Field(ge=0, le=99)]]


class FloatSearch(StrictModel):
    type: Literal["float"] = "float"
    low: PositiveFloat = 0.25
    high: PositiveFloat = 4.0
    log: bool = True
    base_adaptor: PositiveFloat = 0.0001
    base_segmentation_detection: PositiveFloat = 0.0002

    @model_validator(mode="after")
    def validate_bounds(self) -> FloatSearch:
        if self.low > self.high:
            raise ValueError("learning_rate_multiplier.low must be <= high")
        return self


class IntChoices(StrictModel):
    type: Literal["categorical"] = "categorical"
    choices: list[Annotated[int, Field(gt=0)]]


class LayerChoices(StrictModel):
    type: Literal["categorical"] = "categorical"
    choices: list[list[Literal["layer2", "layer3"]]]


class PreprocessingSearch(StrictModel):
    image_size: IntChoices
    normalization: Literal["imagenet"] = "imagenet"
    interpolation: Literal["bilinear"] = "bilinear"
    antialias: Literal[True] = True


class SearchSpace(StrictModel):
    learning_rate_multiplier: FloatSearch
    batch_size: IntChoices
    epochs: IntChoices
    feature_layers: LayerChoices
    preprocessing: PreprocessingSearch


class SamplerSettings(StrictModel):
    name: Literal["TPESampler"] = "TPESampler"
    seed: int = 42
    startup_trials: Annotated[StrictInt, Field(ge=0)] = 5


class PrunerSettings(StrictModel):
    name: Literal["MedianPruner"] = "MedianPruner"
    startup_trials: Annotated[int, Field(ge=0)] = 5
    warmup_epochs: Annotated[int, Field(ge=0)] = 40
    interval_epochs: Annotated[int, Field(gt=0)] = 10


class ThresholdSettings(StrictModel):
    method: Literal["training_percentile"] = "training_percentile"
    percentile: Annotated[float, Field(gt=0.0, le=100.0)] = 99
    score_source: Literal["supersimplenet.pred_score"] = "supersimplenet.pred_score"
    value: Annotated[float, Field(ge=0.0, le=1.0)] | None = None


class NormalOnlySettings(StrictModel):
    percentile: Annotated[float, Field(gt=0.0, le=100.0)] = 99
    train_ratio: Probability = 0.8
    validation_ratio: Probability = 0.2
    seed: int = 42

    @model_validator(mode="after")
    def validate_ratios(self) -> NormalOnlySettings:
        if not math.isclose(self.train_ratio + self.validation_ratio, 1.0):
            raise ValueError("normal_only train_ratio + validation_ratio must equal 1")
        if self.train_ratio == 0 or self.validation_ratio == 0:
            raise ValueError("normal_only ratios must both be positive")
        return self


class ExecutionSettings(StrictModel):
    trials: Annotated[int, Field(gt=0)] = 10
    seed: int = 42


class OptunaSettings(StrictModel):
    search: SearchSpace
    sampler: SamplerSettings
    pruner: PrunerSettings
    threshold: ThresholdSettings
    normal_only: NormalOnlySettings
    execution: ExecutionSettings


class ScoreSettings(StrictModel):
    source: Literal["supersimplenet.pred_score"] = "supersimplenet.pred_score"
    anomalib_post_processor: Literal[False] = False
    anomalib_evaluator: Literal[False] = False
    anomalib_visualizer: Literal[False] = False


class SyntheticFloatRange(StrictModel):
    min: float
    max: float

    @field_validator("min", "max", mode="before")
    @classmethod
    def validate_number(cls, value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("synthetic_anomaly bounds must be finite numbers")
        try:
            finite = math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            raise ValueError("synthetic_anomaly bounds must be finite numbers")
        return value


class NoiseStdRange(SyntheticFloatRange):
    min: float = 0.010
    max: float = 0.020

    @model_validator(mode="after")
    def validate_bounds(self) -> NoiseStdRange:
        if not 0 < self.min <= self.max:
            raise ValueError("noise_std requires 0 < min <= max")
        return self


class PerlinThresholdRange(SyntheticFloatRange):
    min: float = 0.2
    max: float = 0.4

    @model_validator(mode="after")
    def validate_bounds(self) -> PerlinThresholdRange:
        if not 0 <= self.min <= self.max < 1:
            raise ValueError("perlin_threshold requires 0 <= min <= max < 1")
        return self


class PerlinScaleExponentRange(StrictModel):
    min: StrictInt = 0
    max: StrictInt = 5

    @model_validator(mode="after")
    def validate_bounds(self) -> PerlinScaleExponentRange:
        if not 0 <= self.min <= self.max <= 5:
            raise ValueError("perlin_scale_exponent requires 0 <= min <= max <= 5")
        return self


class SyntheticAnomalySettings(StrictModel):
    noise_std: NoiseStdRange = Field(default_factory=NoiseStdRange)
    perlin_threshold: PerlinThresholdRange = Field(default_factory=PerlinThresholdRange)
    perlin_scale_exponent: PerlinScaleExponentRange = Field(
        default_factory=PerlinScaleExponentRange
    )


class EnabledProbability(StrictModel):
    enabled: bool = True
    probability: Probability


class TranslationSettings(EnabledProbability):
    max_ratio: Annotated[float, Field(ge=0.0, le=1.0)] = 0.02
    padding_mode: Literal["reflection"] = "reflection"


class RotationSettings(EnabledProbability):
    max_degrees: Annotated[float, Field(ge=0.0, le=180.0)] = 3.0
    padding_mode: Literal["reflection"] = "reflection"


class FactorSettings(EnabledProbability):
    factor_min: PositiveFloat
    factor_max: PositiveFloat

    @model_validator(mode="after")
    def validate_factor_bounds(self) -> FactorSettings:
        if self.factor_min > self.factor_max:
            raise ValueError("factor_min must be <= factor_max")
        return self


class ColorTemperatureSettings(EnabledProbability):
    base_kelvin: Annotated[int, Field(ge=1000, le=40000)] = 6500
    max_delta_kelvin: Annotated[int, Field(ge=0)] = 500

    @model_validator(mode="after")
    def validate_kelvin_bounds(self) -> ColorTemperatureSettings:
        if self.base_kelvin - self.max_delta_kelvin < 1000:
            raise ValueError("color_temperature minimum must be >= 1000K")
        if self.base_kelvin + self.max_delta_kelvin > 40000:
            raise ValueError("color_temperature maximum must be <= 40000K")
        return self


class SensorNoiseSettings(EnabledProbability):
    stddev_min: Annotated[float, Field(ge=0.0)] = 0.0
    stddev_max: Annotated[float, Field(ge=0.0)] = 0.01

    @model_validator(mode="after")
    def validate_stddev_bounds(self) -> SensorNoiseSettings:
        if self.stddev_min > self.stddev_max:
            raise ValueError("stddev_min must be <= stddev_max")
        return self


class BlurSettings(EnabledProbability):
    enabled: bool = False
    kernel_sizes: list[Annotated[int, Field(gt=0)]]
    sigma_min: PositiveFloat = 0.1
    sigma_max: PositiveFloat = 1.0

    @model_validator(mode="after")
    def validate_blur(self) -> BlurSettings:
        if any(size % 2 == 0 for size in self.kernel_sizes):
            raise ValueError("blur.kernel_sizes must contain positive odd integers")
        if self.sigma_min > self.sigma_max:
            raise ValueError("blur.sigma_min must be <= sigma_max")
        return self


AugmentationName = Literal[
    "translation",
    "rotation",
    "brightness",
    "contrast",
    "color_temperature",
    "gamma",
    "sensor_noise",
    "blur",
]


class AugmentationSettings(StrictModel):
    enabled: bool = True
    seed: int = 42
    order: list[AugmentationName]
    translation: TranslationSettings
    rotation: RotationSettings
    brightness: FactorSettings
    contrast: FactorSettings
    color_temperature: ColorTemperatureSettings
    gamma: FactorSettings
    sensor_noise: SensorNoiseSettings
    blur: BlurSettings

    @model_validator(mode="after")
    def validate_order(self) -> AugmentationSettings:
        if len(self.order) != len(set(self.order)):
            raise ValueError("augmentation.order must not contain duplicates")
        return self


class OrbAlignmentSettings(StrictModel):
    knn_k: Literal[2] = 2
    ratio_threshold: Annotated[float, Field(gt=0.0, lt=1.0)] = 0.75
    minimum_matches: Annotated[int, Field(ge=4)] = 10
    ransac_reprojection_threshold_px: PositiveFloat = 8.0
    ransac_confidence: Annotated[float, Field(gt=0.0, lt=1.0)] = 0.95
    minimum_inlier_ratio: Probability = 0.2


class EccAlignmentSettings(StrictModel):
    min_correlation: Annotated[float, Field(gt=0.0, le=1.0)]
    max_translation_ratio: Annotated[float, Field(gt=0.0, le=0.1)] = 0.1
    max_rotation_degrees: Annotated[float, Field(gt=0.0, le=10.0)] = 10.0
    min_scale: Annotated[float, Field(ge=0.9, le=1.0)] = 0.9
    max_scale: Annotated[float, Field(ge=1.0, le=1.1)] = 1.1

    @field_validator(
        "min_correlation",
        "max_translation_ratio",
        "max_rotation_degrees",
        "min_scale",
        "max_scale",
        mode="before",
    )
    @classmethod
    def require_finite_number(cls, value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("ECC alignment parameters must be finite numbers")
        try:
            finite = math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            raise ValueError("ECC alignment parameters must be finite numbers")
        return value


class AlignmentSettings(StrictModel):
    method: Literal["ORB", "ECC", "NONE"] = "ORB"
    orb: OrbAlignmentSettings | None = None
    ecc: EccAlignmentSettings | None = None

    @model_validator(mode="after")
    def validate_method_settings(self) -> AlignmentSettings:
        if self.method == "ORB":
            if self.ecc is not None:
                raise ValueError("alignment.ecc is not valid for ORB")
            if self.orb is None:
                self.orb = OrbAlignmentSettings()
        elif self.method == "ECC":
            if self.orb is not None or self.ecc is None:
                raise ValueError("ECC requires alignment.ecc and forbids alignment.orb")
        elif self.orb is not None or self.ecc is not None:
            raise ValueError("NONE forbids alignment.orb and alignment.ecc")
        return self


class BrightnessNormalizationSettings(StrictModel):
    enabled: StrictBool = True
    statistic: Literal["median", "mean"] = "median"
    exclude_above: Annotated[StrictInt, Field(ge=1, le=255)] = 230
    exclude_below: Annotated[StrictInt, Field(ge=0, le=254)] = 0
    min_gain: PositiveFloat = 0.5
    max_gain: PositiveFloat = 2.0

    @field_validator("min_gain", "max_gain", mode="before")
    @classmethod
    def validate_finite_gain(cls, value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("brightness_normalization gain must be a finite number")
        try:
            finite = math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            raise ValueError("brightness_normalization gain must be a finite number")
        return value

    @model_validator(mode="after")
    def validate_bounds(self) -> BrightnessNormalizationSettings:
        if self.exclude_below >= self.exclude_above:
            raise ValueError(
                "brightness_normalization.exclude_below must be less than exclude_above"
            )
        if self.min_gain > self.max_gain:
            raise ValueError("brightness_normalization.min_gain must be <= max_gain")
        return self


class GroupRangeConfig(StrictModel):
    id: Annotated[StrictInt, Field(ge=0, le=99)]
    inspection_threshold: Annotated[float, Field(ge=0.0, le=1.0)] | None
    heatmap_range: HeatmapRange

    @field_validator("inspection_threshold", mode="before")
    @classmethod
    def validate_inspection_threshold(cls, value: object) -> object:
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(
                    "inspection_threshold must be a finite JSON number or null"
                )
            try:
                finite = math.isfinite(value)
            except OverflowError:
                finite = False
            if not finite:
                raise ValueError(
                    "inspection_threshold must be a finite JSON number or null"
                )
        return value


class GroupConfig(StrictModel):
    id: Annotated[StrictInt, Field(ge=0)]
    ranges: list[GroupRangeConfig] = Field(min_length=1)
    optuna_settings: OptunaSettings
    score: ScoreSettings
    augmentation: AugmentationSettings
    synthetic_anomaly: SyntheticAnomalySettings = Field(
        default_factory=SyntheticAnomalySettings
    )

    @model_validator(mode="before")
    @classmethod
    def validate_range_entries(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        group_id = value.get("id", "unknown")
        ranges = value.get("ranges")
        if ranges is None:
            raise ValueError(f"group {group_id} ranges is required")
        if not isinstance(ranges, list) or not ranges:
            raise ValueError(f"group {group_id} ranges must be a nonempty array")
        for index, item in enumerate(ranges):
            split_id = (
                item.get("id", "missing") if isinstance(item, dict) else "missing"
            )
            try:
                GroupRangeConfig.model_validate(item)
            except ValidationError as error:
                first = error.errors()[0]
                field = ".".join(str(part) for part in first["loc"])
                raise ValueError(
                    f"group {group_id} range {split_id} at ranges[{index}] "
                    f"{field}: {first['msg']}"
                ) from error
        return value

    @property
    def range_ids(self) -> list[int]:
        return [item.id for item in self.ranges]

    @model_validator(mode="after")
    def validate_group(self) -> GroupConfig:
        seen_ids: set[int] = set()
        for range_id in self.range_ids:
            if range_id in seen_ids:
                raise ValueError(f"group {self.id} range {range_id} is duplicated")
            seen_ids.add(range_id)
        if self.score.source != self.optuna_settings.threshold.score_source:
            raise ValueError(
                f"group {self.id} score.source must equal threshold.score_source"
            )
        return self


class ModelConfig(StrictModel):
    base: str
    ranges: list[CropRange] = Field(alias="range")
    blacklist: list[BlacklistEntry]
    alignment: AlignmentSettings
    brightness_normalization: BrightnessNormalizationSettings = Field(
        default_factory=lambda: BrightnessNormalizationSettings(enabled=False)
    )
    groups: list[GroupConfig] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def combine_group_details(cls, value: object) -> object:
        if not isinstance(value, dict) or "groups" not in value:
            return value
        groups = value["groups"]
        details = value.get("group_detail")
        if not isinstance(details, dict):
            raise ValueError("group_detail must be an object")
        if not isinstance(groups, list):
            return value

        summary_fields = {
            "id",
            "ranges",
        }
        detail_fields = {
            "optuna_settings",
            "score",
            "augmentation",
            "synthetic_anomaly",
        }
        group_ids: list[int] = []
        for group in groups:
            if not isinstance(group, dict):
                return value
            misplaced = set(group) - summary_fields
            if misplaced:
                deprecated = misplaced & {
                    "range_ids",
                    "inspection_threshold",
                    "heatmap_range",
                }
                if deprecated:
                    raise ValueError(
                        f"group {group.get('id', 'unknown')} 廃止された項目: "
                        f"{sorted(deprecated)}"
                    )
                raise ValueError(
                    f"group {group.get('id', 'unknown')} contains misplaced fields: "
                    f"{sorted(misplaced)}"
                )
            group_id = group.get("id")
            if (
                isinstance(group_id, bool)
                or not isinstance(group_id, int)
                or group_id < 0
            ):
                return value
            group_ids.append(group_id)

        for key, detail in details.items():
            if not isinstance(key, str) or re.fullmatch(r"0|[1-9][0-9]*", key) is None:
                raise ValueError(f"group_detail has invalid id key: {key!r}")
            if not isinstance(detail, dict):
                raise ValueError(f"group_detail[{key!r}] must be an object")
            misplaced = set(detail) - detail_fields
            if misplaced:
                deprecated = misplaced & {
                    "range_ids",
                    "inspection_threshold",
                    "heatmap_range",
                }
                if deprecated:
                    raise ValueError(
                        f"group_detail[{key!r}] 廃止された項目: {sorted(deprecated)}"
                    )
                raise ValueError(
                    f"group_detail[{key!r}] contains misplaced fields: "
                    f"{sorted(misplaced)}"
                )

        expected = {str(group_id) for group_id in group_ids}
        actual = set(details)
        if expected != actual:
            raise ValueError(
                "group_detail ids must match groups.id: "
                f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
            )
        return {
            **{key: item for key, item in value.items() if key != "group_detail"},
            "groups": [{**group, **details[str(group["id"])]} for group in groups],
        }

    @field_validator("base")
    @classmethod
    def validate_base_filename(cls, value: str) -> str:
        if (
            not value
            or value in {".", ".."}
            or "/" in value
            or "\\" in value
            or Path(value).is_absolute()
        ):
            raise ValueError("base must be a filename without path components")
        return value

    @model_validator(mode="after")
    def validate_cross_fields(self) -> ModelConfig:
        ids = [item.id for item in self.ranges]
        if len(ids) != len(set(ids)):
            raise ValueError("range.id must be unique")
        valid_ids = set(ids)
        for entry in self.blacklist:
            unknown = set(entry.id) - valid_ids
            if unknown:
                raise ValueError(f"blacklist references unknown range ids: {unknown}")
        group_ids = [group.id for group in self.groups]
        if len(group_ids) != len(set(group_ids)):
            duplicate = next(
                group_id for group_id in group_ids if group_ids.count(group_id) > 1
            )
            raise ValueError(f"group {duplicate} groups.id must be unique")
        for group in self.groups:
            unknown = set(group.range_ids) - valid_ids
            if unknown:
                raise ValueError(
                    f"group {group.id} range {sorted(unknown)[0]} references unknown range id"
                )
        return self

    def select_groups(self, group: int | None = None) -> list[GroupConfig]:
        selected = sorted(self.groups, key=lambda item: item.id)
        if group is None:
            return selected
        for item in selected:
            if item.id == group:
                return [item]
        raise ValueError(
            f"unknown group {group}; available groups: {[item.id for item in selected]}"
        )

    def ranges_for(self, group: GroupConfig) -> list[CropRange]:
        selected = set(group.range_ids)
        return [item for item in self.ranges if item.id in selected]


class AppConfig(StrictModel):
    image_size: Annotated[int, Field(gt=0)]
    image_resize: Annotated[float, Field(gt=0.0, le=1.0)] = 1.0
    model: str
    part: ModelConfig


def load_image_settings(path: Path) -> tuple[int, float]:
    parser = configparser.ConfigParser(inline_comment_prefixes=None)
    if not parser.read(path, encoding="utf-8"):
        raise ValueError(f"setting.ini not found: {path}")
    try:
        raw = parser["IMAGE"]["SIZE"]
    except KeyError as error:
        raise ValueError("setting.ini requires IMAGE.SIZE") from error
    unknown_sections = sorted(set(parser.sections()) - {"IMAGE"})
    unknown_keys = sorted(set(parser["IMAGE"]) - {"size", "resize"})
    if unknown_sections or unknown_keys:
        details = []
        if unknown_sections:
            details.append(f"sections={unknown_sections}")
        if unknown_keys:
            details.append(f"IMAGE keys={unknown_keys}")
        warnings.warn(
            f"setting.ini contains unknown entries: {', '.join(details)}",
            UserWarning,
            stacklevel=2,
        )
    try:
        size = int(raw.strip(), 10)
    except ValueError as error:
        raise ValueError("IMAGE.SIZE must be a positive decimal integer") from error
    if size <= 0:
        raise ValueError("IMAGE.SIZE must be a positive decimal integer")
    raw_resize = parser["IMAGE"].get("RESIZE", "1")
    try:
        resize = float(raw_resize.strip())
    except ValueError as error:
        raise ValueError("IMAGE.RESIZE must be greater than 0 and at most 1") from error
    if not math.isfinite(resize) or not 0 < resize <= 1:
        raise ValueError("IMAGE.RESIZE must be greater than 0 and at most 1")
    return size, resize


def load_image_size(path: Path) -> int:
    return load_image_settings(path)[0]


def load_model_config(path: Path) -> ModelConfig:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"model config not found: {path.name}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON in {path.name}: {error.msg}") from error
    if isinstance(payload, dict):
        payload = {
            key: value
            for key, value in payload.items()
            if not key.startswith("_comment")
        }
    return ModelConfig.model_validate(payload)


def load_config(root: Path, model: str) -> AppConfig:
    validate_model_name(model)
    paths = ProjectPaths(root)
    image_size, image_resize = load_image_settings(paths.global_config)
    config = AppConfig(
        image_size=image_size,
        image_resize=image_resize,
        model=model,
        part=load_model_config(paths.model_config(model)),
    )
    paths.base_image(model, config.part.base)
    return config


def validate_blacklist_images(config: AppConfig, available_images: set[str]) -> None:
    unknown = {entry.image for entry in config.part.blacklist} - available_images
    if unknown:
        raise ValueError(f"blacklist references unknown images: {sorted(unknown)}")


def preparation_fingerprint(
    config: AppConfig, *, group: GroupConfig | None = None, testing: bool = False
) -> str:
    """Hash only settings that determine prepared image pixels and membership."""
    part = config.part
    payload: dict[str, object] = {
        "base": part.base,
        "range": [item.model_dump() for item in part.ranges],
        "alignment": part.alignment.model_dump(),
        "image_size": config.image_size,
        "image_resize": config.image_resize,
    }
    brightness = part.brightness_normalization
    payload["brightness_normalization"] = (
        brightness.model_dump() if brightness.enabled else {"enabled": False}
    )
    if group is not None:
        if not testing:
            payload["blacklist"] = [item.model_dump() for item in part.blacklist]
        payload["group"] = group.id
        payload["range_ids"] = group.range_ids
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_threshold(
    path: Path, value: float, *, group: int, destination: Path | None = None
) -> None:
    """Write a threshold-updated configuration without mutating other fields."""

    validated = load_model_config(path)
    if group not in {item.id for item in validated.groups}:
        raise ValueError(f"unknown group {group} in {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["group_detail"][str(group)]["optuna_settings"]["threshold"]["value"] = value
    target = destination or path
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=4) + "\n", encoding="utf-8"
        )
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()
