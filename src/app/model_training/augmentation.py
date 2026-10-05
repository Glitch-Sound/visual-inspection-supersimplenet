"""Configured training-only image augmentation."""

from __future__ import annotations

import math
from typing import Any, cast

import cv2
import numpy as np
from numpy.typing import NDArray
from torchvision.transforms.v2 import Transform

from app.common.config import AugmentationSettings

FloatImage = NDArray[np.float32]


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
