from __future__ import annotations

import json
import pickle
import shutil
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import optuna
import pytest
import torch
from conftest import build_project, write_test_image

from app.common.artifact_transaction import (
    _transaction_path,
    recover_artifact_transaction,
)
from app.common.contracts import (
    AlignmentResult,
    BestTrialResult,
    PreparationManifest,
    PreparedSource,
    PreparedSplit,
    ScoreContract,
    TrialParametersContract,
)
from app.common.model_adapter import TunableSupersimplenet
from app.common.runtime import DeviceSelection
from app.model_training import artifacts
from app.model_training.artifacts import persist_best_trial, restart_training
from app.model_training.augmentation import AugmentationPipeline
from app.model_training.cli import format_training_summary
from app.model_training.search import (
    DatasetSplit,
    TrialOutcome,
    TrialParameters,
    create_study,
    run_search,
    split_by_source,
)
from app.model_training.trainer import AnomalibTrialRunner, ensure_cached

TRIAL_PARAMETERS = {
    "learning_rate_multiplier": 1.0,
    "batch_size": 4,
    "epochs": 200,
    "feature_layers": ["layer2"],
    "image_size": 256,
}


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


def set_trial_parameters(trial: optuna.Trial) -> None:
    trial.suggest_float("learning_rate_multiplier", 1.0, 1.0)
    trial.suggest_categorical("batch_size", [4])
    trial.suggest_categorical("epochs", [200])
    trial.suggest_categorical("feature_layers", ['["layer2"]'])
    trial.suggest_categorical("image_size", [256])


def make_manifest(count: int) -> PreparationManifest:
    return PreparationManifest(
        model="XX",
        created_at=datetime.now(UTC),
        sources=[
            PreparedSource(
                source_image=f"source-{index}.png",
                alignment=AlignmentResult(status="aligned"),
                splits=[
                    PreparedSplit(
                        source_image=f"source-{index}.png",
                        split_id=split_id,
                        image=f"source-{index}_{split_id:02d}.png",
                    )
                    for split_id in range(2)
                ],
            )
            for index in range(count)
        ],
    )


def test_split_groups_by_source_image(tmp_path: Path) -> None:
    manifest = make_manifest(10)
    first = split_by_source(manifest, tmp_path, seed=42)
    second = split_by_source(manifest, tmp_path, seed=42)
    assert first == second
    assert len(first.train_sources) == 8
    assert set(first.train_sources).isdisjoint(first.validation_sources)
    assert {path.name.rsplit("_", 1)[0] + ".png" for path in first.train_images} == set(
        first.train_sources
    )


def test_split_rejects_insufficient_source_images(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="current count is 1"):
        split_by_source(make_manifest(1), tmp_path)


def test_search_selects_lowest_validation_percentile(tmp_path: Path) -> None:
    config, _paths = build_project(tmp_path)
    study = create_study(config, tmp_path / "study.db")
    assert vars(study.pruner)["_n_startup_trials"] == 5
    assert vars(study.pruner)["_n_warmup_steps"] == 40
    assert vars(study.pruner)["_interval_steps"] == 10
    checkpoint = tmp_path / "candidate.ckpt"
    torch.save({"state_dict": {}}, checkpoint)

    def runner(
        parameters: TrialParameters, split: DatasetSplit, trial: optuna.Trial
    ) -> TrialOutcome:
        del parameters, split
        if trial.number == 1:
            raise RuntimeError("simulated failure")
        if trial.number == 2:
            raise optuna.TrialPruned()
        return TrialOutcome([trial.number / 100], [0.1, 0.2], checkpoint)

    split = split_by_source(make_manifest(5), tmp_path)
    study, outcomes = run_search(config, split, study, runner)
    assert len(study.trials) == 10
    assert study.best_trial.number == 0
    assert 0 in outcomes
    assert {trial.state.name for trial in study.trials} >= {
        "COMPLETE",
        "FAIL",
        "PRUNED",
    }


def test_search_report_labels_objective_as_provisional() -> None:
    result = BestTrialResult(
        model="XX",
        trial_number=0,
        parameters=TrialParametersContract.model_validate(TRIAL_PARAMETERS),
        objective=0.12,
        checkpoint="weights/XX.ckpt",
        score_contract=ScoreContract(),
        threshold=0.2,
        train_sources=["a.png"],
        validation_sources=["b.png"],
        seed=42,
        dependencies={},
    )
    summary = format_training_summary(result)
    assert "暫定探索指標" in summary
    assert "accuracy" not in summary.lower()


def test_augmentation_is_training_only_and_ephemeral(tmp_path: Path) -> None:
    config, _paths = build_project(tmp_path)
    settings = config.part.augmentation
    for name in settings.order:
        item = getattr(settings, name)
        setattr(settings, name, item.model_copy(update={"probability": 1.0}))
    source = np.linspace(0, 1, 16 * 16 * 3, dtype=np.float32).reshape(16, 16, 3)
    source_before = source.copy()
    output = AugmentationPipeline(settings)(source, training=True)
    assert output.shape == source.shape
    assert float(output.min()) >= 0.0 and float(output.max()) <= 1.0
    assert np.array_equal(source, source_before)
    assert list(tmp_path.iterdir()) == [tmp_path / "config"]


def test_blur_template_default_and_opt_in(tmp_path: Path) -> None:
    config, _paths = build_project(tmp_path)
    settings = config.part.augmentation.model_copy(deep=True)
    for name in settings.order:
        item = getattr(settings, name)
        setattr(settings, name, item.model_copy(update={"enabled": False}))
    source = np.zeros((9, 9, 3), dtype=np.float32)
    source[4, 4] = 1.0

    assert settings.blur.enabled is False
    assert np.array_equal(AugmentationPipeline(settings)(source, training=True), source)

    settings.blur = settings.blur.model_copy(
        update={"enabled": True, "probability": 1.0}
    )
    blurred = AugmentationPipeline(settings)(source, training=True)
    assert not np.array_equal(blurred, source)
    assert np.array_equal(
        AugmentationPipeline(settings)(source, training=False), source
    )


def test_validation_pipeline_disables_augmentation(tmp_path: Path) -> None:
    config, _paths = build_project(tmp_path)
    source = np.full((8, 8, 3), 0.5, dtype=np.float32)
    output = AugmentationPipeline(config.part.augmentation)(source, training=False)
    assert np.array_equal(output, source)


def test_training_persists_best_model_and_threshold(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path)
    checkpoint = tmp_path / "trial.ckpt"
    torch.save({"state_dict": {}}, checkpoint)
    study = optuna.create_study(direction="minimize")
    trial = study.ask()
    set_trial_parameters(trial)
    study.tell(trial, 0.1)
    split = split_by_source(make_manifest(5), tmp_path)
    result = persist_best_trial(
        config=config,
        paths=paths,
        split=split,
        study=study,
        outcomes={0: TrialOutcome([0.1], [0.1, 0.2, 0.3], checkpoint)},
    )
    payload = torch.load(paths.checkpoint("XX"), weights_only=True)
    saved_config = json.loads(paths.model_config("XX").read_text(encoding="utf-8"))
    assert result.threshold == pytest.approx(float(np.percentile([0.1, 0.2, 0.3], 99)))
    assert payload["visual_inspection"]["threshold"] == result.threshold
    assert saved_config["optuna_settings"]["threshold"]["value"] == result.threshold
    assert (paths.study_dir("XX") / "best_trial.json").is_file()


def test_training_artifact_transaction_restores_previous_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, paths = build_project(tmp_path)
    checkpoint = paths.checkpoint("XX")
    checkpoint.parent.mkdir(parents=True)
    torch.save({"state_dict": {"old": torch.tensor([1])}}, checkpoint)
    best = paths.study_dir("XX") / "best_trial.json"
    best.parent.mkdir(parents=True)
    best.write_text('{"old": true}\n', encoding="utf-8")
    config_path = paths.model_config("XX")
    old_bytes = {
        "checkpoint": checkpoint.read_bytes(),
        "config": config_path.read_bytes(),
        "best": best.read_bytes(),
    }

    candidate = tmp_path / "candidate.ckpt"
    torch.save({"state_dict": {"new": torch.tensor([2])}}, candidate)
    study = optuna.create_study(direction="minimize")
    trial = study.ask()
    set_trial_parameters(trial)
    study.tell(trial, 0.1)
    split = split_by_source(make_manifest(5), tmp_path)
    replace = artifacts._replace_staged_artifact
    calls = 0

    def fail_second(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated replacement failure")
        replace(source, target)

    monkeypatch.setattr(artifacts, "_replace_staged_artifact", fail_second)

    with pytest.raises(OSError, match="simulated replacement failure"):
        persist_best_trial(
            config=config,
            paths=paths,
            split=split,
            study=study,
            outcomes={0: TrialOutcome([0.1], [0.2, 0.3], candidate)},
        )

    assert checkpoint.read_bytes() == old_bytes["checkpoint"]
    assert config_path.read_bytes() == old_bytes["config"]
    assert best.read_bytes() == old_bytes["best"]
    assert not (paths.study_dir("XX") / ".artifact-transaction.json").exists()

    targets = {
        "checkpoint": checkpoint,
        "config": config_path,
        "best_trial": best,
    }
    for target in targets.values():
        shutil.copy2(target, _transaction_path(target, "backup"))
        target.write_bytes(b"incomplete-new-artifact")
    artifacts._write_transaction_journal(
        paths.study_dir("XX") / ".artifact-transaction.json",
        {name: True for name in targets},
    )

    recover_artifact_transaction(paths, "XX")

    assert checkpoint.read_bytes() == old_bytes["checkpoint"]
    assert config_path.read_bytes() == old_bytes["config"]
    assert best.read_bytes() == old_bytes["best"]


def test_pretrained_weights_are_cached(tmp_path: Path) -> None:
    calls: list[Path] = []

    def fetch(path: Path) -> None:
        calls.append(path)
        path.write_bytes(b"weights")

    target = tmp_path / "pretrained" / "model.bin"
    ensure_cached(target, fetch)
    ensure_cached(target, fetch)
    assert target.read_bytes() == b"weights"
    assert len(calls) == 1


def test_training_resumes_existing_study(tmp_path: Path) -> None:
    config, _paths = build_project(tmp_path)
    split = split_by_source(make_manifest(5), tmp_path)
    checkpoint = tmp_path / "candidate.ckpt"
    torch.save({}, checkpoint)

    def runner(
        parameters: TrialParameters, split: DatasetSplit, trial: optuna.Trial
    ) -> TrialOutcome:
        del parameters, split, trial
        return TrialOutcome([0.1], [0.1], checkpoint)

    first_config = config.model_copy(
        update={
            "part": config.part.model_copy(
                update={
                    "optuna_settings": config.part.optuna_settings.model_copy(
                        update={
                            "execution": config.part.optuna_settings.execution.model_copy(
                                update={"trials": 2}
                            )
                        }
                    )
                }
            )
        }
    )
    storage = tmp_path / "resume.db"
    study, _ = run_search(
        first_config, split, create_study(first_config, storage), runner
    )
    assert len(study.trials) == 2
    resumed, _ = run_search(config, split, create_study(config, storage), runner)
    assert len(resumed.trials) == 10
    assert resumed.trials[0].number == 0


def test_training_restart_replaces_only_derived_artifacts(tmp_path: Path) -> None:
    _config, paths = build_project(tmp_path)
    paths.study_dir("XX").mkdir(parents=True)
    (paths.study_dir("XX") / "study.db").write_text("old", encoding="utf-8")
    paths.checkpoint("XX").parent.mkdir(parents=True)
    paths.checkpoint("XX").write_text("old", encoding="utf-8")
    paths.pretrained.mkdir(parents=True)
    cached = paths.pretrained / "cache.bin"
    cached.write_text("keep", encoding="utf-8")
    original = paths.original_train("XX") / "base.png"
    original.parent.mkdir(parents=True)
    original.write_text("keep", encoding="utf-8")
    restart_training(paths, "XX")
    assert not paths.study_dir("XX").exists()
    assert not paths.checkpoint("XX").exists()
    assert cached.read_text(encoding="utf-8") == "keep"
    assert original.read_text(encoding="utf-8") == "keep"
    assert paths.model_config("XX").is_file()
