"""Model evaluation, visualization, aggregation, and restart handling."""

from __future__ import annotations

import math
import shutil
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import cv2
import numpy as np

from app.common.atomic import recover_directory_swap
from app.common.config import AppConfig
from app.common.contracts import (
    BestTrialResult,
    HeatmapRange,
    InspectionResult,
    PreparationManifest,
    ResultStatus,
    RunMetadata,
    ScoreContract,
    SplitResult,
)
from app.common.image_io import ImageArray, read_image, write_image
from app.common.paths import ProjectPaths
from app.model_evaluation.predictor import Prediction, load_checkpoint_metadata
from app.model_evaluation.results import aggregate_status, write_inspection_result

Predictor = Callable[[ImageArray], Prediction]


def _ignore_message(_message: str) -> None:
    """Default sink for callers that do not need command-level messages."""


def validate_score_contract(
    config: AppConfig, checkpoint_metadata: dict[str, object]
) -> float:
    threshold = config.part.optuna_settings.threshold.value
    if threshold is None:
        raise ValueError(
            "optuna_settings.threshold.value is required before evaluation"
        )
    expected_source = config.part.score.source
    if checkpoint_metadata.get("model") != config.model:
        raise ValueError(
            f"checkpoint model mismatch: expected {config.model}, "
            f"got {checkpoint_metadata.get('model')}"
        )
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
    return threshold


def effective_threshold(config: AppConfig, provisional_threshold: float) -> float:
    override = config.part.inspection_threshold
    return provisional_threshold if override is None else override


def require_heatmap_range(config: AppConfig) -> HeatmapRange:
    heatmap_range = config.part.heatmap_range
    if heatmap_range is None:
        raise ValueError("heatmap_range is required for evaluation")
    return heatmap_range


def validate_best_trial_contract(
    config: AppConfig, paths: ProjectPaths, best: BestTrialResult
) -> None:
    expected_checkpoint = str(paths.checkpoint(config.model).relative_to(paths.root))
    threshold = config.part.optuna_settings.threshold.value
    if best.model != config.model:
        raise ValueError(
            f"best_trial model mismatch: expected {config.model}, got {best.model}"
        )
    if best.checkpoint != expected_checkpoint:
        raise ValueError(
            "best_trial checkpoint mismatch: "
            f"expected {expected_checkpoint}, got {best.checkpoint}"
        )
    if threshold is None or not np.isclose(best.threshold, threshold):
        raise ValueError("best_trial threshold does not match model config")
    parameters = best.parameters
    search = config.part.optuna_settings.search
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
    split_id: int,
    threshold: float,
    heatmap_range: HeatmapRange,
    predictor: Predictor,
    result_path: Path,
) -> SplitResult:
    image = read_image(image_path)
    prediction = predictor(image)
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
    )


def evaluate_model(
    config: AppConfig,
    paths: ProjectPaths,
    *,
    predictor: Predictor,
    finish_runtime: Callable[[], RunMetadata],
    record_warning: Callable[[str], None] = _ignore_message,
    record_error: Callable[[str], None] = _ignore_message,
    on_threshold_selected: Callable[[float], None] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    checkpoint_metadata: dict[str, object] | None = None,
) -> list[InspectionResult]:
    heatmap_range = require_heatmap_range(config)
    checkpoint = paths.checkpoint(config.model)
    metadata = (
        load_checkpoint_metadata(checkpoint)
        if checkpoint_metadata is None
        else checkpoint_metadata
    )
    provisional_threshold = validate_score_contract(config, metadata)
    threshold = effective_threshold(config, provisional_threshold)
    if on_threshold_selected is not None:
        on_threshold_selected(threshold)
    prepared_dir = paths.prepared_test(config.model)
    manifest = PreparationManifest.read_json(prepared_dir / "manifest.json")
    if manifest.model != config.model:
        raise ValueError(
            f"test manifest model mismatch: expected {config.model}, "
            f"got {manifest.model}"
        )
    total_sources = len(manifest.sources)
    if on_progress is not None:
        on_progress(0, total_sources)
    target = paths.results(config.model)
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = recover_directory_swap(target)
    stage = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent))
    pending_results: list[dict[str, object]] = []
    required_ids = {item.id for item in config.part.ranges}
    try:
        for processed, source in enumerate(manifest.sources, start=1):
            split_results: list[SplitResult] = []
            errors: list[str] = []
            warnings: list[str] = []
            if source.alignment.status != "aligned":
                warning = source.alignment.reason or "alignment_failed"
                warnings.append(warning)
                record_warning(f"{source.source_image}: {warning}")
            for split in source.splits:
                image_path = prepared_dir / split.image
                result_name = f"{split.image}_result.png"
                try:
                    split_results.append(
                        evaluate_split(
                            image_path=image_path,
                            split_id=split.split_id,
                            threshold=threshold,
                            heatmap_range=heatmap_range,
                            predictor=predictor,
                            result_path=stage / result_name,
                        )
                    )
                except Exception as error:  # keep remaining splits observable
                    message = f"split {split.split_id}: {error}"
                    errors.append(message)
                    record_error(f"{source.source_image}: {message}")
                    split_results.append(
                        SplitResult(
                            split_id=split.split_id,
                            image=split.image,
                            score=None,
                            status=ResultStatus.ERROR,
                            error=message,
                        )
                    )
            overall, next_action = aggregate_status(
                split_results, required_split_ids=required_ids
            )
            pending_results.append(
                {
                    "source_image": source.source_image,
                    "model": config.model,
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
                }
            )
            if on_progress is not None:
                on_progress(processed, total_sources)
        runtime = finish_runtime()
        results = [
            InspectionResult.model_validate({**values, "runtime": runtime})
            for values in pending_results
        ]
        for result in results:
            write_inspection_result(result, stage / f"{result.source_image}.json")
        if target.exists():
            target.replace(backup)
        stage.replace(target)
        if backup.exists():
            shutil.rmtree(backup)
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        if backup.exists() and not target.exists():
            backup.replace(target)
        raise
    return results


def restart_evaluation(paths: ProjectPaths, model: str) -> None:
    paths.remove_model_artifact(paths.results(model), expected=paths.results(model))
