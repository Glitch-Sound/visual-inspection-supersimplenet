"""Shared SuperSimpleNet model construction."""

from __future__ import annotations

from typing import Any, cast

import torch
import torch.nn.functional as F
from anomalib.data.utils.generators import generate_perlin_noise
from anomalib.models import Supersimplenet
from anomalib.models.image.supersimplenet.anomaly_generator import AnomalyGenerator
from torch.optim import AdamW
from torch.optim.lr_scheduler import MultiStepLR

from app.common.config import SyntheticAnomalySettings

BACKBONE_NAME = "wide_resnet50_2.tv_in1k"


class ConfiguredAnomalyGenerator(AnomalyGenerator):
    """Anomalib 2.6.2 generator with settings sampled for each mask."""

    def __init__(self, settings: SyntheticAnomalySettings) -> None:
        super().__init__(noise_mean=0.0, noise_std=0.0, threshold=0.0)
        self.settings = settings

    @staticmethod
    def _sample_float(low: float, high: float) -> float:
        return low + (high - low) * torch.rand(1).item()

    @staticmethod
    def _sample_exponent(low: int, high: int) -> int:
        return int(torch.randint(low, high + 1, (1,)).item())

    def generate_perlin(self, batches: int, height: int, width: int) -> torch.Tensor:
        perlin: list[torch.Tensor] = []
        for _ in range(batches):
            exponent = self.settings.perlin_scale_exponent
            scale = (
                2 ** self._sample_exponent(exponent.min, exponent.max),
                2 ** self._sample_exponent(exponent.min, exponent.max),
            )
            perlin_height = max(self.next_power_2(height), scale[0] * 2)
            perlin_width = max(self.next_power_2(width), scale[1] * 2)
            threshold_range = self.settings.perlin_threshold
            threshold = self._sample_float(threshold_range.min, threshold_range.max)
            perlin_noise = generate_perlin_noise(
                height=perlin_height, width=perlin_width, scale=scale
            )

            if not (perlin_noise > threshold).any():
                perlin_noise = (perlin_noise - perlin_noise.min()) / (
                    perlin_noise.max() - perlin_noise.min()
                )
                perlin_noise = (perlin_noise * 2) - 1

            perlin_noise = F.interpolate(
                perlin_noise.reshape(1, 1, perlin_height, perlin_width),
                size=(height, width),
                mode="bilinear",
            )
            thresholded_perlin = torch.where(perlin_noise > threshold, 1, 0)
            if torch.rand(1).item() > 0.5:
                thresholded_perlin = torch.zeros_like(thresholded_perlin)
            perlin.append(thresholded_perlin)
        return torch.cat(perlin)

    def forward(
        self,
        input_features: torch.Tensor | None,
        adapted_features: torch.Tensor,
        masks: torch.Tensor,
        labels: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        batch_size, _, height, width = masks.shape
        adapted_features = torch.cat((adapted_features, adapted_features))
        mask = torch.cat((masks, masks))
        labels = torch.cat((labels, labels))
        if input_features is not None:
            input_features = torch.cat((input_features, input_features))

        std_range = self.settings.noise_std
        stds = torch.tensor(
            [
                self._sample_float(std_range.min, std_range.max)
                for _ in range(batch_size * 2)
            ],
            device=adapted_features.device,
            dtype=adapted_features.dtype,
        ).reshape(batch_size * 2, 1, 1, 1)
        noise = (
            torch.randn(
                adapted_features.shape,
                device=adapted_features.device,
                dtype=adapted_features.dtype,
                requires_grad=False,
            )
            * stds
        )

        noise_mask = torch.ones(
            batch_size * 2,
            1,
            height,
            width,
            device=adapted_features.device,
            requires_grad=False,
        )
        noise_mask = noise_mask * (1 - mask)
        perlin_mask = self.generate_perlin(batch_size * 2, height, width).to(
            adapted_features.device
        )
        noise_mask = noise_mask * perlin_mask
        mask = mask + noise_mask
        mask = torch.where(mask > 0, torch.ones_like(mask), torch.zeros_like(mask))
        new_anomalous = (
            noise_mask.reshape(batch_size * 2, -1).any(dim=1).type(torch.float32)
        )
        labels = labels + new_anomalous
        labels = torch.where(
            labels > 0, torch.ones_like(labels), torch.zeros_like(labels)
        )
        perturbed_adapt = adapted_features + noise * noise_mask
        perturbed_feat = (
            input_features + noise * noise_mask if input_features is not None else None
        )
        return cast(torch.Tensor, perturbed_feat), perturbed_adapt, mask, labels


class TunableSupersimplenet(Supersimplenet):
    """SuperSimpleNet with a trial-specific learning rate multiplier."""

    def __init__(self, *, learning_rate_multiplier: float, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.learning_rate_multiplier = learning_rate_multiplier

    def configure_optimizers(self):
        adaptor = cast(Any, self.model.adaptor)
        segmentation_detector = cast(Any, self.model.segdec)
        optimizer = AdamW(
            [
                {
                    "params": adaptor.parameters(),
                    "lr": 0.0001 * self.learning_rate_multiplier,
                },
                {
                    "params": segmentation_detector.parameters(),
                    "lr": 0.0002 * self.learning_rate_multiplier,
                    "weight_decay": 0.00001,
                },
            ]
        )
        max_epochs = int(self.trainer.max_epochs or 0)
        scheduler = MultiStepLR(
            optimizer,
            milestones=[int(max_epochs * 0.8), int(max_epochs * 0.9)],
            gamma=0.4,
        )
        return [optimizer], [scheduler]


def create_supersimplenet(
    *,
    layers: list[str],
    image_size: int,
    learning_rate_multiplier: float,
    synthetic_anomaly: SyntheticAnomalySettings | None = None,
):
    """Build Anomalib SuperSimpleNet with the fixed raw-score contract."""

    model = TunableSupersimplenet(
        learning_rate_multiplier=learning_rate_multiplier,
        backbone=BACKBONE_NAME,
        layers=layers,
        pre_processor=TunableSupersimplenet.configure_pre_processor(
            (image_size, image_size)
        ),
        post_processor=False,
        evaluator=False,
        visualizer=False,
    )
    if synthetic_anomaly is not None:
        model.model.anomaly_generator = ConfiguredAnomalyGenerator(synthetic_anomaly)
    return model
