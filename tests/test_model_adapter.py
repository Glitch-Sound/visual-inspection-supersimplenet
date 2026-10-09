from __future__ import annotations

import pickle
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import optuna
import pytest
import torch
from conftest import write_test_image

from app.common.model_adapter import TunableSupersimplenet
from app.common.runtime import DeviceSelection
from app.model_training.search import DatasetSplit, TrialParameters
from app.model_training.trainer import AnomalibTrialRunner

TRIAL_PARAMETERS = {
    "learning_rate_multiplier": 1.0,
    "batch_size": 4,
    "epochs": 200,
    "feature_layers": ["layer2"],
    "image_size": 256,
}


def test_model_adapter_uses_tv_backbone(monkeypatch: pytest.MonkeyPatch) -> None:
    import timm

    from app.common import model_adapter

    captured: dict[str, object] = {}
    original_create = cast(Any, timm.create_model)

    def create_without_download(model_name: str, *args: Any, **kwargs: Any) -> Any:
        captured["backbone"] = model_name
        captured["pretrained"] = kwargs["pretrained"]
        kwargs["pretrained"] = False
        return original_create(model_name, *args, **kwargs)

    monkeypatch.setattr(timm, "create_model", create_without_download)
    model = model_adapter.create_supersimplenet(
        layers=["layer2", "layer3"], image_size=256, learning_rate_multiplier=1.0
    )

    assert captured == {
        "backbone": "wide_resnet50_2.tv_in1k",
        "pretrained": True,
    }
    feature_extractor = cast(Any, model.model.feature_extractor)
    assert feature_extractor.get_channels_dim() == 1536


def test_trial_runner_uses_all_validation_images(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import anomalib.data
    import anomalib.engine

    folder_options: dict[str, object] = {}
    predicted_paths: list[Path] = []

    def fake_folder(**kwargs: object) -> object:
        folder_options.update(kwargs)
        return object()

    class FakeEngine:
        def __init__(self, **_kwargs: object) -> None:
            self.trainer = self

        def fit(self, _model: object, *, datamodule: object) -> None:
            del datamodule

        def save_checkpoint(self, path: Path) -> None:
            path.write_bytes(b"checkpoint")

        def predict(
            self, *, model: object, data_path: Path, return_predictions: bool
        ) -> list[dict[str, float]]:
            del model, return_predictions
            predicted_paths.append(data_path)
            return [{"pred_score": 0.1}]

    monkeypatch.setattr(anomalib.data, "Folder", fake_folder)
    monkeypatch.setattr(anomalib.engine, "Engine", FakeEngine)
    monkeypatch.setattr(
        "app.model_training.trainer.create_supersimplenet", lambda **_kwargs: object()
    )
    train_image = tmp_path / "train.png"
    validation_images = [tmp_path / f"validation-{index}.png" for index in range(2)]
    for path in (train_image, *validation_images):
        path.write_bytes(b"image")
    split = DatasetSplit(
        train_images=(train_image,),
        validation_images=tuple(validation_images),
        train_sources=("train.png",),
        validation_sources=("validation.png",),
    )
    trial = optuna.create_study().ask()
    parameters = TrialParameters(**TRIAL_PARAMETERS)
    runner = AnomalibTrialRunner(
        tmp_path / "work", DeviceSelection("cpu", "test", "test")
    )
    runner(parameters, split, trial)

    assert folder_options["val_split_mode"] == "same_as_test"
    assert "val_split_ratio" not in folder_options
    validation_dir = folder_options["normal_test_dir"]
    assert isinstance(validation_dir, Path)
    assert len(list(validation_dir.iterdir())) == len(validation_images)
    assert predicted_paths[0] == validation_dir


def test_anomalib_uses_complete_validation_folder(tmp_path: Path) -> None:
    from anomalib.data import Folder

    train_dir = tmp_path / "train"
    validation_dir = tmp_path / "validation"
    write_test_image(train_dir / "train.png")
    for index in range(2):
        write_test_image(validation_dir / f"validation-{index}.png")

    datamodule = Folder(
        name="validation-contract",
        normal_dir=train_dir,
        normal_test_dir=validation_dir,
        val_split_mode="same_as_test",
        num_workers=0,
    )
    datamodule.setup()

    assert len(datamodule.val_data) == 2
    assert len(datamodule.test_data) == 2


def test_tunable_model_is_pickleable_and_uses_trial_multiplier() -> None:
    model = TunableSupersimplenet.__new__(TunableSupersimplenet)
    from lightning.pytorch import LightningModule

    LightningModule.__init__(model)
    model.learning_rate_multiplier = 2.0
    core = torch.nn.Module()
    core.add_module("adaptor", torch.nn.Linear(1, 1))
    core.add_module("segdec", torch.nn.Linear(1, 1))
    model.model = core
    cast(Any, model)._trainer = SimpleNamespace(max_epochs=200)

    optimizers, schedulers = model.configure_optimizers()
    serialized = pickle.dumps(model)

    assert serialized
    assert model.learning_rate_multiplier == 2.0
    assert [group["lr"] for group in optimizers[0].param_groups] == pytest.approx(
        [0.0002, 0.0004]
    )
    assert schedulers[0].milestones == {160: 1, 180: 1}


def test_tunable_model_saves_lightning_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lightning.pytorch import Trainer
    from torch.utils.data import DataLoader, TensorDataset

    core = torch.nn.Module()
    core.add_module("adaptor", torch.nn.Linear(1, 1))
    core.add_module("segdec", torch.nn.Linear(1, 1))
    monkeypatch.setattr(
        "anomalib.models.image.supersimplenet.lightning_model.SupersimplenetModel",
        lambda **_kwargs: core,
    )

    def train_step(
        self: TunableSupersimplenet, batch: tuple[torch.Tensor], batch_idx: int
    ) -> torch.Tensor:
        del batch_idx
        core_model = cast(Any, self.model)
        output = core_model.segdec(core_model.adaptor(batch[0]))
        return output.square().mean()

    monkeypatch.setattr(TunableSupersimplenet, "training_step", train_step)
    monkeypatch.setattr(TunableSupersimplenet, "configure_callbacks", lambda self: [])
    model = TunableSupersimplenet(
        learning_rate_multiplier=2.0,
        pre_processor=TunableSupersimplenet.configure_pre_processor((8, 8)),
        post_processor=False,
        evaluator=False,
        visualizer=False,
    )
    trainer = Trainer(
        default_root_dir=tmp_path,
        max_epochs=1,
        limit_train_batches=1,
        accelerator="cpu",
        devices=1,
        logger=False,
        enable_checkpointing=False,
        enable_model_summary=False,
        enable_progress_bar=False,
    )
    loader = DataLoader(TensorDataset(torch.ones(2, 1)), batch_size=2)
    trainer.fit(model, train_dataloaders=loader)
    checkpoint = tmp_path / "model.ckpt"
    trainer.save_checkpoint(checkpoint)

    payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
    assert checkpoint.is_file()
    assert payload["hyper_parameters"]["pre_processor"] is not None
    assert "model.adaptor.weight" in payload["state_dict"]


def test_group_req_007_s02(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import timm.models._hub as hub
    from timm.models.resnet import ResNet

    from app.common.model_adapter import create_supersimplenet

    cache_file = tmp_path / "hf-cache" / "model.bin"
    downloads: list[Path] = []
    cache_lookups: list[tuple[str, str]] = []

    def cached_download(repo_id: str, *, filename: str, **_kwargs: object) -> str:
        cache_lookups.append((repo_id, filename))
        if not cache_file.exists():
            cache_file.parent.mkdir(parents=True)
            cache_file.write_bytes(b"test weights")
            downloads.append(cache_file)
        return str(cache_file)

    def read_cached_weights(path: str, **_kwargs: object) -> dict[str, object]:
        assert Path(path) == cache_file
        assert cache_file.read_bytes() == b"test weights"
        return {}

    monkeypatch.setattr(hub, "_has_safetensors", False)
    monkeypatch.setattr(hub, "hf_hub_download", cached_download)
    monkeypatch.setattr(hub, "_torch_load", read_cached_weights)
    monkeypatch.setattr(
        ResNet,
        "load_state_dict",
        lambda _self, _state, **_kwargs: SimpleNamespace(
            missing_keys=[], unexpected_keys=[]
        ),
    )

    for _ in range(2):
        model = create_supersimplenet(
            layers=["layer2"], image_size=256, learning_rate_multiplier=1.0
        )
        del model

    assert cache_lookups == [
        ("timm/wide_resnet50_2.tv_in1k", "pytorch_model.bin"),
        ("timm/wide_resnet50_2.tv_in1k", "pytorch_model.bin"),
    ]
    assert downloads == [cache_file]


def test_model_creation_uses_real_hub_cache_while_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import safetensors.torch as safetensors_torch
    from huggingface_hub import constants, file_download
    from timm.models.resnet import ResNet

    from app.common.model_adapter import create_supersimplenet

    cache_root = tmp_path / "hub"
    monkeypatch.setattr(constants, "HF_HUB_CACHE", str(cache_root))
    storage = cache_root / file_download.repo_folder_name(
        repo_id="timm/wide_resnet50_2.tv_in1k", repo_type="model"
    )
    commit = "0" * 40
    reference = storage / "refs" / "main"
    reference.parent.mkdir(parents=True)
    reference.write_text(commit, encoding="utf-8")
    cached_weights = storage / "snapshots" / commit / "model.safetensors"
    cached_weights.parent.mkdir(parents=True)
    cached_weights.write_bytes(b"cached test weights")
    metadata_lookups: list[bool] = []

    def offline_metadata(
        **_kwargs: object,
    ) -> tuple[None, None, None, None, None, OSError]:
        metadata_lookups.append(True)
        return None, None, None, None, None, OSError("offline")

    def read_cached_weights(path: str, **_kwargs: object) -> dict[str, object]:
        assert Path(path) == cached_weights
        return {}

    monkeypatch.setattr(file_download, "_get_metadata_or_catch_error", offline_metadata)
    monkeypatch.setattr(safetensors_torch, "load_file", read_cached_weights)
    monkeypatch.setattr(
        ResNet,
        "load_state_dict",
        lambda _self, _state, **_kwargs: SimpleNamespace(
            missing_keys=[], unexpected_keys=[]
        ),
    )

    for _ in range(2):
        model = create_supersimplenet(
            layers=["layer2"], image_size=256, learning_rate_multiplier=1.0
        )
        del model

    assert metadata_lookups == [True, True]
    assert cached_weights.read_bytes() == b"cached test weights"
