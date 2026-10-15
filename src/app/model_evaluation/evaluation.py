"""Model evaluation, visualization, aggregation, and restart handling."""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import cv2
import numpy as np

from app.common.config import AppConfig, GroupConfig, preparation_fingerprint
from app.common.contracts import (
    BestTrialResult,
    HeatmapRange,
    InspectionResult,
    ResultStatus,
    RunMetadata,
    ScoreContract,
    SplitResult,
    SplitThreshold,
    ThresholdSource,
    load_preparation_manifest,
)
from app.common.image_io import ImageArray, read_image, write_image
from app.common.paths import ProjectPaths
from app.model_evaluation.predictor import Prediction, load_checkpoint_metadata
from app.model_evaluation.results import aggregate_status, write_inspection_result

Predictor = Callable[[ImageArray], Prediction]


def _ignore_message(_message: str) -> None:
    """Default sink for callers that do not need command-level messages."""


def validate_score_contract(
    config: AppConfig, group: GroupConfig, checkpoint_metadata: dict[str, object]
) -> float:
    threshold = group.optuna_settings.threshold.value
    if threshold is None:
        raise ValueError(
            "optuna_settings.threshold.value is required before evaluation"
        )
    expected_source = group.score.source
    if checkpoint_metadata.get("model") != config.model:
        raise ValueError(
            f"checkpoint model mismatch: expected {config.model}, "
            f"got {checkpoint_metadata.get('model')}"
        )
    if checkpoint_metadata.get("group") != group.id:
        raise ValueError(f"checkpoint group mismatch: expected {group.id}")
    if checkpoint_metadata.get("score_source") != expected_source:
        raise ValueError("checkpoint score_source does not match model config")
    if checkpoint_metadata.get("anomalib_post_processor") is not False:
        raise ValueError("checkpoint must have anomalib_post_processor disabled")
    checkpoint_threshold = checkpoint_metadata.get("threshold")
    if (
        isinstance(checkpoint_threshold, bool)
        or not isinstance(checkpoint_threshold, (int, float))
        or not np.isclose(checkpoint_threshold, threshold)
    ):
        raise ValueError("checkpoint threshold does not match model config")
    settings = group.optuna_settings.threshold
    if settings.unit == "split":
        if checkpoint_metadata.get("threshold_unit") != "split":
            raise ValueError("checkpoint threshold unit does not match model config")
        if checkpoint_metadata.get("min_score_count") != settings.min_score_count:
            raise ValueError("checkpoint min_score_count does not match model config")
        _validate_split_thresholds(
            group,
            checkpoint_metadata.get("split_thresholds"),
            label="checkpoint",
        )
    elif checkpoint_metadata.get("threshold_unit", "group") != "group":
        raise ValueError("checkpoint threshold unit does not match model config")
    return threshold


def _validate_split_thresholds(
    group: GroupConfig, candidate: object, *, label: str
) -> None:
    settings = group.optuna_settings.threshold
    expected = settings.split_values
    if set(expected) != {str(item) for item in group.range_ids}:
        raise ValueError("model config split thresholds must cover range_ids")
    if not isinstance(candidate, dict) or set(candidate) != set(expected):
        raise ValueError(f"{label} split threshold ids do not match model config")
    for key, value in candidate.items():
        try:
            actual = SplitThreshold.model_validate(value)
        except ValueError as error:
            raise ValueError(
                f"{label} split threshold {key} is invalid: {error}"
            ) from error
        planned = expected[key]
        if (
            not np.isclose(actual.value, planned.value)
            or actual.source != planned.source
            or actual.score_count != planned.score_count
        ):
            raise ValueError(
                f"{label} split threshold {key} does not match model config"
            )


def effective_threshold(group: GroupConfig, provisional_threshold: float) -> float:
    override = group.inspection_threshold
    return provisional_threshold if override is None else override


def require_heatmap_range(group: GroupConfig) -> HeatmapRange:
    heatmap_range = group.heatmap_range
    if heatmap_range is None:
        raise ValueError("heatmap_range is required for evaluation")
    return heatmap_range


def validate_best_trial_contract(
    config: AppConfig, group: GroupConfig, paths: ProjectPaths, best: BestTrialResult
) -> None:
    expected_checkpoint = str(
        paths.checkpoint(config.model, group.id).relative_to(paths.root)
    )
    threshold = group.optuna_settings.threshold.value
    if best.model != config.model:
        raise ValueError(
            f"best_trial model mismatch: expected {config.model}, got {best.model}"
        )
    if best.group != group.id or set(best.range_ids) != set(group.range_ids):
        raise ValueError(f"best_trial group or range_ids mismatch: expected {group.id}")
    if best.checkpoint != expected_checkpoint:
        raise ValueError(
            "best_trial checkpoint mismatch: "
            f"expected {expected_checkpoint}, got {best.checkpoint}"
        )
    if threshold is None or not np.isclose(best.threshold, threshold):
        raise ValueError("best_trial threshold does not match model config")
    settings = group.optuna_settings.threshold
    if best.threshold_method != settings.method:
        raise ValueError("best_trial threshold method does not match model config")
    if best.threshold_percentile is not None and not np.isclose(
        best.threshold_percentile, settings.percentile
    ):
        raise ValueError("best_trial threshold percentile does not match model config")
    if not np.isclose(best.threshold_margin, settings.margin):
        raise ValueError("best_trial threshold margin does not match model config")
    if best.threshold_unit != settings.unit:
        raise ValueError("best_trial threshold unit does not match model config")
    if settings.unit == "split":
        if best.min_score_count != settings.min_score_count:
            raise ValueError("best_trial min_score_count does not match model config")
        _validate_split_thresholds(
            group,
            {key: item.model_dump() for key, item in best.split_thresholds.items()},
            label="best_trial",
        )
    if settings.method == "out_of_fold_percentile":
        expected_folds = (
            len(best.final_train_sources)
            if settings.folds == "leave_one_out"
            else settings.folds
        )
        if len(best.cross_validation) != expected_folds:
            raise ValueError(
                "best_trial cross-validation folds do not match model config"
            )
    parameters = best.parameters
    search = group.optuna_settings.search
    if not (
        search.learning_rate_multiplier.low
        <= parameters.learning_rate_multiplier
        <= search.learning_rate_multiplier.high
    ):
        raise ValueError("best_trial learning_rate_multiplier is outside search space")
    if parameters.batch_size not in search.batch_size.choices:
        raise ValueError("best_trial batch_size is outside search space")
    if parameters.epochs not in search.epochs.choices:
        raise ValueError("best_trial epochs is outside search space")
    if list(parameters.feature_layers) not in search.feature_layers.choices:
        raise ValueError("best_trial feature_layers is outside search space")
    if parameters.image_size not in search.preprocessing.image_size.choices:
        raise ValueError("best_trial image_size is outside search space")


def _heatmap(
    image: ImageArray, anomaly_map: np.ndarray, heatmap_range: HeatmapRange
) -> ImageArray:
    height, width = image.shape[:2]
    resized = cv2.resize(anomaly_map.astype(np.float32), (width, height))
    lower, upper = heatmap_range.min, heatmap_range.max
    span = upper - lower
    if not math.isfinite(span):
        normalized_values = (resized.astype(np.float64) / 2 - lower / 2) / (
            upper / 2 - lower / 2
        )
    else:
        normalized_values = (resized.astype(np.float64) - lower) / span
    normalized = (np.clip(normalized_values, 0.0, 1.0) * 255).astype(np.uint8)
    colored = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)
    return cast(ImageArray, cv2.addWeighted(image, 0.55, colored, 0.45, 0))


def evaluate_split(
    *,
    image_path: Path,
    image: ImageArray,
    prediction: Prediction,
    split_id: int,
    threshold: float,
    heatmap_range: HeatmapRange,
    result_path: Path,
    threshold_source: ThresholdSource = "group_calculated",
) -> SplitResult:
    status = (
        ResultStatus.ANOMALY if prediction.score >= threshold else ResultStatus.NORMAL
    )
    output = (
        image
        if status == ResultStatus.NORMAL
        else cast(
            ImageArray,
            cv2.hconcat(
                [image, _heatmap(image, prediction.anomaly_map, heatmap_range)]
            ),
        )
    )
    write_image(result_path, output)
    return SplitResult(
        split_id=split_id,
        image=image_path.name,
        score=prediction.score,
        status=status,
        result_image=result_path.name,
        threshold=threshold,
        threshold_source=threshold_source,
    )


def evaluate_model(
    config: AppConfig,
    group: GroupConfig,
    paths: ProjectPaths,
    *,
    predictor: Predictor,
    output_dir: Path,
    finish_runtime: Callable[[], RunMetadata],
    record_warning: Callable[[str], None] = _ignore_message,
    record_error: Callable[[str], None] = _ignore_message,
    on_threshold_selected: Callable[[float], None] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    checkpoint_metadata: dict[str, object] | None = None,
) -> list[InspectionResult]:
    heatmap_range = require_heatmap_range(group)
    checkpoint = paths.checkpoint(config.model, group.id)
    metadata = (
        load_checkpoint_metadata(checkpoint)
        if checkpoint_metadata is None
        else checkpoint_metadata
    )
    provisional_threshold = validate_score_contract(config, group, metadata)
    settings = group.optuna_settings.threshold
    threshold = (
        effective_threshold(group, provisional_threshold)
        if settings.unit == "group"
        else provisional_threshold
    )
    if on_threshold_selected is not None:
        on_threshold_selected(threshold)
    prepared_dir = paths.prepared_test(config.model)
    manifest = load_preparation_manifest(
        prepared_dir,
        model=config.model,
        allowed_split_ids={item.id for item in config.part.ranges},
        fingerprint=preparation_fingerprint(config),
    )
    total_sources = len(manifest.sources)
    if on_progress is not None:
        on_progress(0, total_sources)
    output_dir.mkdir(parents=True, exist_ok=False)
    results: list[InspectionResult] = []
    required_ids = set(group.range_ids)
    for source in manifest.sources:
        split_results: list[SplitResult] = []
        errors: list[str] = []
        warnings: list[str] = []
        if source.alignment.status != "aligned":
            warning = source.alignment.reason or "alignment_failed"
            warnings.append(warning)
            record_warning(f"group {group.id} {source.source_image}: {warning}")
        available_splits = source.splits if source.alignment.status == "aligned" else []
        for split in available_splits:
            if split.split_id not in required_ids:
                continue
            threshold_source: ThresholdSource
            if settings.unit == "split":
                key = str(split.split_id)
                override = group.inspection_threshold_by_split.get(key)
                if override is not None:
                    applied_threshold = override
                    threshold_source = "manual_override"
                else:
                    learned = settings.split_values[key]
                    applied_threshold = learned.value
                    threshold_source = (
                        "split_calculated"
                        if learned.source == "calculated"
                        else "group_fallback"
                    )
            else:
                applied_threshold = threshold
                threshold_source = (
                    "group_manual_override"
                    if group.inspection_threshold is not None
                    else "group_calculated"
                )
            image_path = prepared_dir / split.image
            result_name = f"{split.image}_result.png"
            try:
                image = read_image(image_path)
                prediction = predictor(image)
            except Exception as error:
                message = f"split {split.split_id}: {error}"
                errors.append(message)
                record_error(f"group {group.id} {source.source_image}: {message}")
                split_results.append(
                    SplitResult(
                        split_id=split.split_id,
                        image=split.image,
                        score=None,
                        status=ResultStatus.ERROR,
                        error=message,
                        threshold=applied_threshold,
                        threshold_source=threshold_source,
                    )
                )
            else:
                split_results.append(
                    evaluate_split(
                        image_path=image_path,
                        image=image,
                        prediction=prediction,
                        split_id=split.split_id,
                        threshold=applied_threshold,
                        threshold_source=threshold_source,
                        heatmap_range=heatmap_range,
                        result_path=output_dir / result_name,
                    )
                )
        overall, next_action = aggregate_status(
            split_results, required_split_ids=required_ids
        )
        result = InspectionResult.model_validate(
            {
                "source_image": source.source_image,
                "model": config.model,
                "group": group.id,
                "range_ids": group.range_ids,
                "checkpoint": str(checkpoint.relative_to(paths.root)),
                "score_contract": ScoreContract(),
                "threshold": threshold,
                "heatmap_range": heatmap_range,
                "splits": split_results,
                "overall_status": overall,
                "processed_at": datetime.now(UTC),
                "alignment": source.alignment,
                "errors": errors,
                "warnings": warnings,
                "next_action": next_action,
                "runtime": finish_runtime(),
            }
        )
        write_inspection_result(result, output_dir / f"{result.source_image}.json")
        results.append(result)
        if on_progress is not None:
            on_progress(len(results), total_sources)
    return results
