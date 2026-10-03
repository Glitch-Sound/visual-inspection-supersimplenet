"""Model evaluation, visualization, aggregation, and restart handling."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import cv2
import numpy as np

from app.config import AppConfig
from app.contracts import (
    InspectionResult,
    PreparationManifest,
    ResultStatus,
    ScoreContract,
    SplitResult,
)
from app.imaging import ImageArray, read_image, write_image
from app.modeling import Prediction, load_checkpoint_metadata
from app.paths import ProjectPaths
from app.results import aggregate_status, write_inspection_result

Predictor = Callable[[ImageArray], Prediction]


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
    if not isinstance(checkpoint_threshold, (int, float)) or not np.isclose(
        checkpoint_threshold, threshold
    ):
        raise ValueError("checkpoint threshold does not match model config")
    return threshold


def _heatmap(image: ImageArray, anomaly_map: np.ndarray) -> ImageArray:
    height, width = image.shape[:2]
    resized = cv2.resize(anomaly_map.astype(np.float32), (width, height))
    minimum, maximum = float(resized.min()), float(resized.max())
    normalized = (
        np.zeros_like(resized, dtype=np.uint8)
        if np.isclose(minimum, maximum)
        else ((resized - minimum) / (maximum - minimum) * 255).astype(np.uint8)
    )
    colored = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)
    return cast(ImageArray, cv2.addWeighted(image, 0.55, colored, 0.45, 0))


def evaluate_split(
    *,
    image_path: Path,
    split_id: int,
    threshold: float,
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
        else _heatmap(image, prediction.anomaly_map)
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
    runtime: dict[str, object],
) -> list[InspectionResult]:
    checkpoint = paths.checkpoint(config.model)
    metadata = load_checkpoint_metadata(checkpoint)
    threshold = validate_score_contract(config, metadata)
    prepared_dir = paths.prepared_test(config.model)
    manifest = PreparationManifest.read_json(prepared_dir / "manifest.json")
    target = paths.results(config.model)
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent))
    backup = target.with_name(f".{target.name}.backup")
    results: list[InspectionResult] = []
    required_ids = {item.id for item in config.part.ranges}
    try:
        for source in manifest.sources:
            split_results: list[SplitResult] = []
            errors: list[str] = []
            warnings: list[str] = []
            if source.alignment.status != "aligned":
                warnings.append(source.alignment.reason or "alignment_failed")
            for split in source.splits:
                image_path = prepared_dir / split.image
                result_name = f"{Path(split.image).stem}_result.png"
                try:
                    split_results.append(
                        evaluate_split(
                            image_path=image_path,
                            split_id=split.split_id,
                            threshold=threshold,
                            predictor=predictor,
                            result_path=stage / result_name,
                        )
                    )
                except Exception as error:  # keep remaining splits observable
                    message = f"split {split.split_id}: {error}"
                    errors.append(message)
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
            result = InspectionResult(
                source_image=source.source_image,
                model=config.model,
                checkpoint=str(checkpoint.relative_to(paths.root)),
                score_contract=ScoreContract(),
                threshold=threshold,
                splits=split_results,
                overall_status=overall,
                processed_at=datetime.now(UTC),
                alignment=source.alignment,
                errors=errors,
                warnings=warnings,
                runtime=runtime,
                next_action=next_action,
            )
            write_inspection_result(
                result, stage / f"{Path(source.source_image).stem}.json"
            )
            results.append(result)
        if backup.exists():
            shutil.rmtree(backup)
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
