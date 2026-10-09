from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch
from conftest import build_project, write_test_image

from app.common.config import load_config
from app.common.contracts import BestTrialResult, ScoreContract, TrialParametersContract
from app.common.runtime import DeviceSelection, RunRecorder
from app.image_preparation.imaging import AlignedImage
from app.image_preparation.preparation import prepare_testing
from app.model_evaluation.predictor import Prediction


def aligned(
    image: np.ndarray, _reference: np.ndarray, _settings: object
) -> AlignedImage:
    return AlignedImage(image, 20, 0.8)


def project(root: Path, *, two: bool = False, score: float = 0.5):
    config, paths = build_project(
        root,
        ranges=[{"id": 0, "x": 0, "y": 0}, {"id": 1, "x": 8, "y": 0}],
    )
    path = paths.model_config("XX")
    payload = json.loads(path.read_text())
    payload["groups"][0]["range_ids"] = [0, 1]
    if two:
        second = json.loads(json.dumps(payload["groups"][0]))
        second["id"] = 1
        second["range_ids"] = [0]
        payload["groups"].append(second)
    for group in payload["groups"]:
        group["optuna_settings"]["threshold"]["value"] = 0.4
    path.write_text(json.dumps(payload))
    config = load_config(root, "XX")
    for name in ("base.png", "a.png", "b.png"):
        write_test_image(paths.original_train("XX") / name, size=32)
    write_test_image(paths.original_test("XX") / "sample.png", size=32)
    prepare_testing(config, paths, aligner=aligned)
    for group in config.part.groups:
        make_model_artifacts(config, paths, group.id)
    return config, paths


def make_model_artifacts(config, paths, group_id: int) -> None:
    group = config.part.select_groups(group_id)[0]
    threshold = group.optuna_settings.threshold.value
    assert threshold is not None
    checkpoint = paths.checkpoint("XX", group_id)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": {},
            "visual_inspection": {
                "model": "XX",
                "group": group_id,
                "score_source": "supersimplenet.pred_score",
                "anomalib_post_processor": False,
                "threshold": threshold,
            },
        },
        checkpoint,
    )
    best = BestTrialResult(
        model="XX",
        group=group_id,
        range_ids=group.range_ids,
        trial_number=0,
        parameters=TrialParametersContract(
            learning_rate_multiplier=1,
            batch_size=4,
            epochs=100,
            feature_layers=["layer2"],
            image_size=256,
        ),
        objective=0.2,
        checkpoint=str(checkpoint.relative_to(paths.root)),
        score_contract=ScoreContract(),
        threshold=threshold,
        train_sources=["a.png"],
        validation_sources=["b.png"],
        seed=42,
        dependencies={},
    )
    best.write_json(paths.study_dir("XX", group_id) / "best_trial.json")


class FakePredictor:
    def __init__(self, *args, score: float = 0.5, **kwargs):
        self.score = score

    def __call__(self, image: np.ndarray) -> Prediction:
        return Prediction(
            self.score, np.full(image.shape[:2], self.score, dtype=np.float32)
        )


def recorder(command: str = "test") -> RunRecorder:
    return RunRecorder(command, "XX", DeviceSelection("cpu", "CPU", "test"))
