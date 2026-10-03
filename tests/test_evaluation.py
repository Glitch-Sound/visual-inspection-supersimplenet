from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from conftest import build_project, write_test_image

from app.evaluation import evaluate_split, restart_evaluation
from app.modeling import Prediction


def test_evaluation_records_normal_split(tmp_path: Path) -> None:
    image_path = tmp_path / "split.png"
    original = write_test_image(image_path)
    result_path = tmp_path / "result.png"
    result = evaluate_split(
        image_path=image_path,
        split_id=0,
        threshold=0.5,
        predictor=lambda image: Prediction(0.2, np.zeros(image.shape[:2], np.float32)),
        result_path=result_path,
    )
    assert result.status == "normal"
    assert result.score == 0.2
    written = cv2.imread(str(result_path))
    assert written is not None
    assert np.array_equal(written, original)


def test_evaluation_visualizes_anomalous_split(tmp_path: Path) -> None:
    image_path = tmp_path / "split.png"
    original = write_test_image(image_path)
    anomaly_map = np.linspace(
        0, 1, original.shape[0] * original.shape[1], dtype=np.float32
    )
    anomaly_map = anomaly_map.reshape(original.shape[:2])
    result_path = tmp_path / "result.png"
    result = evaluate_split(
        image_path=image_path,
        split_id=0,
        threshold=0.5,
        predictor=lambda _image: Prediction(0.8, anomaly_map),
        result_path=result_path,
    )
    assert result.status == "anomaly"
    written = cv2.imread(str(result_path))
    assert written is not None
    assert not np.array_equal(written, original)


def test_evaluation_restart_replaces_only_results(tmp_path: Path) -> None:
    _config, paths = build_project(tmp_path)
    results = paths.results("XX")
    results.mkdir(parents=True)
    (results / "old.json").write_text("{}", encoding="utf-8")
    checkpoint = paths.checkpoint("XX")
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text("keep", encoding="utf-8")
    prepared = paths.prepared_test("XX")
    prepared.mkdir(parents=True)
    (prepared / "manifest.json").write_text("keep", encoding="utf-8")
    restart_evaluation(paths, "XX")
    assert not results.exists()
    assert checkpoint.read_text(encoding="utf-8") == "keep"
    assert (prepared / "manifest.json").read_text(encoding="utf-8") == "keep"
