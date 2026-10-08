"""Shared SuperSimpleNet model construction."""

from __future__ import annotations

from typing import Any, cast

from anomalib.models import Supersimplenet
from torch.optim import AdamW
from torch.optim.lr_scheduler import MultiStepLR

BACKBONE_NAME = "wide_resnet50_2.tv_in1k"


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
    *, layers: list[str], image_size: int, learning_rate_multiplier: float
):
    """Build Anomalib SuperSimpleNet with the fixed raw-score contract."""

    return TunableSupersimplenet(
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
