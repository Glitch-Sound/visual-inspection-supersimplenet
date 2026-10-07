"""Typed configuration loading and cross-field validation."""

from __future__ import annotations

import configparser
import json
import math
import warnings
from pathlib import Path, PureWindowsPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.paths import ProjectPaths, validate_model_name

Probability = Annotated[float, Field(ge=0.0, le=1.0)]
PositiveFloat = Annotated[float, Field(gt=0.0)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CropRange(StrictModel):
    id: Annotated[int, Field(ge=0, le=99)]
    x: Annotated[int, Field(ge=0)]
    y: Annotated[int, Field(ge=0)]


class BlacklistEntry(StrictModel):
    image: str
    id: list[Annotated[int, Field(ge=0, le=99)]]


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
    resume: bool = True


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


class AlignmentSettings(StrictModel):
    method: Literal["ORB"] = "ORB"
    knn_k: Literal[2] = 2
    ratio_threshold: Annotated[float, Field(gt=0.0, lt=1.0)] = 0.75
    minimum_matches: Annotated[int, Field(ge=4)] = 10
    ransac_reprojection_threshold_px: PositiveFloat = 8.0
    ransac_confidence: Annotated[float, Field(gt=0.0, lt=1.0)] = 0.95
    minimum_inlier_ratio: Probability = 0.2


class ModelConfig(StrictModel):
    base: str
    ranges: list[CropRange] = Field(alias="range")
    blacklist: list[BlacklistEntry]
    inspection_threshold: Annotated[float, Field(ge=0.0, le=1.0)] | None = None
    optuna_settings: OptunaSettings
    score: ScoreSettings
    augmentation: AugmentationSettings
    alignment: AlignmentSettings

    @field_validator("inspection_threshold", mode="before")
    @classmethod
    def validate_inspection_threshold(cls, value: object) -> object:
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(
                "inspection_threshold must be a finite JSON number or null"
            )
        return value

    @field_validator("base")
    @classmethod
    def validate_base_filename(cls, value: str) -> str:
        if (
            not value
            or value in {".", ".."}
            or "/" in value
            or "\\" in value
            or Path(value).is_absolute()
            or PureWindowsPath(value).drive
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
        threshold = self.optuna_settings.threshold
        if self.score.source != threshold.score_source:
            raise ValueError("score.source must equal threshold.score_source")
        return self


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


def write_threshold(
    path: Path, value: float, *, destination: Path | None = None
) -> None:
    """Write a threshold-updated configuration without mutating other fields."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["optuna_settings"]["threshold"]["value"] = value
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
