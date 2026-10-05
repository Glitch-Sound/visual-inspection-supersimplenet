"""Checkpoint predictor using the shared model adapter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import cv2
import numpy as np
from numpy.typing import NDArray

from app.common.model_adapter import create_supersimplenet

FloatImage = NDArray[np.float32]


@dataclass(frozen=True)
class Prediction:
    score: float
    anomaly_map: FloatImage


def rgb_image_tensor(image: NDArray[np.uint8], torch: Any) -> Any:
    """Convert an OpenCV BGR image without duplicating model preprocessing."""

    rgb = np.ascontiguousarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    return torch.from_numpy(rgb).permute(2, 0, 1).float().div(255.0).unsqueeze(0)


def load_checkpoint_metadata(path: Path) -> dict[str, Any]:
    import torch

    payload = torch.load(path, map_location="cpu", weights_only=True)
    metadata = payload.get("visual_inspection")
    if not isinstance(metadata, dict):
        raise ValueError("checkpoint lacks visual_inspection metadata")
    return metadata


class CheckpointPredictor:
    """Raw-score predictor backed by an application-generated checkpoint."""

    def __init__(
        self,
        checkpoint: Path,
        *,
        layers: list[str],
        image_size: int,
        learning_rate_multiplier: float,
        device: str,
    ) -> None:
        import torch

        self.torch = torch
        self.device = torch.device(device)
        self.image_size = image_size
        self.model = create_supersimplenet(
            layers=layers,
            image_size=image_size,
            learning_rate_multiplier=learning_rate_multiplier,
        )
        payload = torch.load(checkpoint, map_location=self.device, weights_only=False)
        self.model.load_state_dict(payload["state_dict"])
        self.model.to(self.device)
        self.model.eval()
        pre_processor = self.model.pre_processor
        if pre_processor is None or pre_processor.transform is None:
            raise ValueError("SuperSimpleNet requires deterministic preprocessing")
        self.preprocess = cast(Any, pre_processor.transform)

    def __call__(self, image: NDArray[np.uint8]) -> Prediction:
        tensor = rgb_image_tensor(image, self.torch)
        tensor = self.preprocess(tensor).to(self.device)
        with self.torch.no_grad():
            output = self.model.model(tensor)
        score = float(output.pred_score.detach().cpu().reshape(-1)[0])
        anomaly_map = (
            output.anomaly_map.detach().cpu().squeeze().numpy().astype(np.float32)
        )
        return Prediction(score=score, anomaly_map=anomaly_map)
