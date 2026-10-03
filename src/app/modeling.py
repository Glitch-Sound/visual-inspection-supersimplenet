"""SuperSimpleNet adapter and deterministic image transforms."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import cv2
import numpy as np
from numpy.typing import NDArray
from torchvision.transforms.v2 import Transform

from app.config import AugmentationSettings

FloatImage = NDArray[np.float32]


@dataclass(frozen=True)
class Prediction:
    score: float
    anomaly_map: FloatImage


def deterministic_preprocess(image: NDArray[np.uint8], image_size: int) -> FloatImage:
    """Resize with bilinear interpolation and return RGB values in [0, 1]."""

    resized = cv2.resize(
        image, (image_size, image_size), interpolation=cv2.INTER_LINEAR
    )
    return cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0


def imagenet_normalize(image: FloatImage) -> FloatImage:
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    return (image - mean) / std


def _temperature_rgb(kelvin: float) -> NDArray[np.float32]:
    """Approximate black-body RGB ratios for 1000K-40000K."""

    temperature = float(np.clip(kelvin, 1000.0, 40000.0)) / 100.0
    if temperature <= 66:
        red = 255.0
        green = 99.4708025861 * math.log(temperature) - 161.1195681661
        blue = (
            0.0
            if temperature <= 19
            else 138.5177312231 * math.log(temperature - 10) - 305.0447927307
        )
    else:
        red = 329.698727446 * ((temperature - 60) ** -0.1332047592)
        green = 288.1221695283 * ((temperature - 60) ** -0.0755148492)
        blue = 255.0
    return np.clip(np.array([red, green, blue], dtype=np.float32), 0, 255) / 255.0


class AugmentationPipeline:
    """Apply configured transforms in order without persisting intermediates."""

    def __init__(self, settings: AugmentationSettings):
        self.settings = settings
        self.rng = np.random.default_rng(settings.seed)

    def __call__(self, image: FloatImage, *, training: bool) -> FloatImage:
        output = image.copy()
        if not training or not self.settings.enabled:
            return output
        for name in self.settings.order:
            setting = getattr(self.settings, name)
            if not setting.enabled or self.rng.random() >= setting.probability:
                continue
            output = getattr(self, f"_{name}")(output, setting)
            output = np.clip(output, 0.0, 1.0).astype(np.float32)
        return output

    def _translation(self, image: FloatImage, setting: Any) -> FloatImage:
        height, width = image.shape[:2]
        dx = self.rng.uniform(-setting.max_ratio, setting.max_ratio) * width
        dy = self.rng.uniform(-setting.max_ratio, setting.max_ratio) * height
        matrix = np.asarray([[1.0, 0.0, dx], [0.0, 1.0, dy]], dtype=np.float32)
        return cast(
            FloatImage,
            cv2.warpAffine(
                image, matrix, (width, height), borderMode=cv2.BORDER_REFLECT_101
            ),
        )

    def _rotation(self, image: FloatImage, setting: Any) -> FloatImage:
        height, width = image.shape[:2]
        angle = self.rng.uniform(-setting.max_degrees, setting.max_degrees)
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
        return cast(
            FloatImage,
            cv2.warpAffine(
                image, matrix, (width, height), borderMode=cv2.BORDER_REFLECT_101
            ),
        )

    def _brightness(self, image: FloatImage, setting: Any) -> FloatImage:
        return image * self.rng.uniform(setting.factor_min, setting.factor_max)

    def _contrast(self, image: FloatImage, setting: Any) -> FloatImage:
        factor = self.rng.uniform(setting.factor_min, setting.factor_max)
        mean = image.mean(axis=(0, 1), keepdims=True)
        return (image - mean) * factor + mean

    def _color_temperature(self, image: FloatImage, setting: Any) -> FloatImage:
        kelvin = self.rng.uniform(
            setting.base_kelvin - setting.max_delta_kelvin,
            setting.base_kelvin + setting.max_delta_kelvin,
        )
        multiplier = _temperature_rgb(kelvin) / _temperature_rgb(setting.base_kelvin)
        return (image * multiplier.reshape(1, 1, 3)).astype(np.float32)

    def _gamma(self, image: FloatImage, setting: Any) -> FloatImage:
        gamma = self.rng.uniform(setting.factor_min, setting.factor_max)
        return np.power(np.clip(image, 0.0, 1.0), gamma)

    def _sensor_noise(self, image: FloatImage, setting: Any) -> FloatImage:
        stddev = self.rng.uniform(setting.stddev_min, setting.stddev_max)
        return image + self.rng.normal(0.0, stddev, image.shape).astype(np.float32)

    def _blur(self, image: FloatImage, setting: Any) -> FloatImage:
        kernel = int(self.rng.choice(setting.kernel_sizes))
        sigma = self.rng.uniform(setting.sigma_min, setting.sigma_max)
        return cast(FloatImage, cv2.GaussianBlur(image, (kernel, kernel), sigma))


class AnomalibTrainingAugmentation(Transform):
    """Adapt the configured NumPy pipeline to Anomalib's tensor transform hook."""

    def __init__(self, settings: AugmentationSettings):
        super().__init__()
        self.pipeline = AugmentationPipeline(settings)

    def transform(self, inpt: Any, params: dict[str, Any]) -> Any:
        import torch

        del params
        tensor = (
            inpt.as_subclass(torch.Tensor) if hasattr(inpt, "as_subclass") else inpt
        )
        device = tensor.device
        source_dtype = tensor.dtype
        array = tensor.detach().cpu().numpy().transpose(1, 2, 0)
        if not tensor.is_floating_point():
            array = array.astype(np.float32) / 255.0
        else:
            array = array.astype(np.float32)
        augmented = self.pipeline(array, training=True)
        result = torch.from_numpy(augmented.transpose(2, 0, 1)).to(device)
        if not tensor.is_floating_point():
            result = (result * 255.0).round().to(source_dtype)
        return result


def ensure_cached(path: Path, fetch: Any) -> Path:
    """Populate a pretrained artifact once without exposing a partial download."""

    if path.is_file():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        fetch(temporary)
        if not temporary.is_file():
            raise OSError("pretrained fetcher did not create the requested artifact")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


def create_supersimplenet(
    *, layers: list[str], image_size: int, learning_rate_multiplier: float
):
    """Build Anomalib SuperSimpleNet with the fixed raw-score contract."""

    from anomalib.models import Supersimplenet
    from torch.optim import AdamW
    from torch.optim.lr_scheduler import MultiStepLR

    class TunableSupersimplenet(Supersimplenet):
        def configure_optimizers(self):
            adaptor = cast(Any, self.model.adaptor)
            segmentation_detector = cast(Any, self.model.segdec)
            optimizer = AdamW(
                [
                    {
                        "params": adaptor.parameters(),
                        "lr": 0.0001 * learning_rate_multiplier,
                    },
                    {
                        "params": segmentation_detector.parameters(),
                        "lr": 0.0002 * learning_rate_multiplier,
                        "weight_decay": 0.00001,
                    },
                ]
            )
            max_epochs = int(self.trainer.max_epochs or 0)
            scheduler = MultiStepLR(
                optimizer,
                milestones=[
                    int(max_epochs * 0.8),
                    int(max_epochs * 0.9),
                ],
                gamma=0.4,
            )
            return [optimizer], [scheduler]

    return TunableSupersimplenet(
        backbone="wide_resnet50_2.tv_in1k",
        layers=layers,
        pre_processor=TunableSupersimplenet.configure_pre_processor(
            (image_size, image_size)
        ),
        post_processor=False,
        evaluator=False,
        visualizer=False,
    )


def extract_predictions(prediction_batches: list[Any]) -> list[float]:
    """Extract raw sigmoid ``pred_score`` values from Anomalib predictions."""

    scores: list[float] = []
    for batch in prediction_batches:
        values = getattr(batch, "pred_score", None)
        if values is None and isinstance(batch, dict):
            values = batch.get("pred_score")
        if values is None:
            raise ValueError("Anomalib prediction does not contain pred_score")
        if hasattr(values, "detach"):
            values = values.detach().cpu().reshape(-1).tolist()
        elif not isinstance(values, list):
            values = [values]
        scores.extend(float(value) for value in values)
    return scores


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

    def __call__(self, image: NDArray[np.uint8]) -> Prediction:
        rgb = deterministic_preprocess(image, self.image_size)
        normalized = imagenet_normalize(rgb)
        tensor = self.torch.from_numpy(normalized.transpose(2, 0, 1)).unsqueeze(0)
        tensor = tensor.to(self.device)
        with self.torch.no_grad():
            output = self.model.model(tensor)
        score = float(output.pred_score.detach().cpu().reshape(-1)[0])
        anomaly_map = (
            output.anomaly_map.detach().cpu().squeeze().numpy().astype(np.float32)
        )
        return Prediction(score=score, anomaly_map=anomaly_map)
