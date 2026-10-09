from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import optuna
import pytest
import torch
import typer
from conftest import build_project, write_test_image

from app.common.config import load_config, preparation_fingerprint
from app.common.contracts import (
    load_preparation_manifest,
)
from app.common.runtime import DeviceSelection, RunRecorder
from app.image_preparation.imaging import AlignedImage
from app.image_preparation.preparation import prepare_training
from app.model_training import cli as training_cli
from app.model_training.artifacts import persist_best_trial
from app.model_training.augmentation import (
    AnomalibTrainingAugmentation,
    AugmentationPipeline,
)
from app.model_training.cli import _train_command
from app.model_training.search import (
    TrialOutcome,
    TrialParameters,
    create_study,
    run_search,
    split_by_source,
)
from app.model_training.trainer import AnomalibTrialRunner


def _aligned(
    image: np.ndarray, _reference: np.ndarray, _settings: object
) -> AlignedImage:
    return AlignedImage(image, 20, 0.8)


def _project(root: Path, *, two: bool = False):
    config, paths = build_project(root)
    if two:
        path = paths.model_config("XX")
        payload = json.loads(path.read_text())
        second = json.loads(json.dumps(payload["groups"][0]))
        second["id"] = 1
        path.write_text(
            json.dumps({**payload, "groups": [payload["groups"][0], second]})
        )
        config = load_config(root, "XX")
    for name in ("base.png", "a.png", "b.png", "c.png"):
        write_test_image(paths.original_train("XX") / name)
    prepare_training(config, paths, aligner=_aligned)
    return config, paths


def _run_cli(monkeypatch: pytest.MonkeyPatch, paths, *, group=None, restart=False):
    recorder = RunRecorder("train", "XX", DeviceSelection("cpu", "CPU", "test"))
    monkeypatch.setattr(
        "app.model_training.cli._run",
        lambda _cmd, _model, action, **_kw: action(paths, recorder),
    )
    return _train_command(model="XX", group=group, restart=restart), recorder


def _stub_search(
    monkeypatch: pytest.MonkeyPatch, paths, *, fail_group: int | None = None
) -> list[int]:
    done: list[int] = []

    class Study:
        trials = []

    monkeypatch.setattr("app.model_training.cli.create_study", lambda *_args: Study())
    monkeypatch.setattr(
        "app.model_training.cli.run_search",
        lambda group, _split, study, _runner, **_kw: (study, {}),
    )
    monkeypatch.setattr(
        "app.model_training.cli.show_trial_conditions", lambda *_args: None
    )

    def persist(*, config, group, paths, split, study, outcomes):
        if group.id == fail_group:
            raise RuntimeError("injected failure")
        done.append(group.id)
        checkpoint = paths.checkpoint(config.model, group.id)
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text(f"group {group.id}")
        return SimpleNamespace(
            trial_number=0,
            threshold=0.4,
            objective=0.2,
            parameters=SimpleNamespace(
                learning_rate_multiplier=1,
                batch_size=4,
                epochs=1,
                feature_layers=["layer2"],
                image_size=256,
            ),
        )

    monkeypatch.setattr("app.model_training.cli.persist_best_trial", persist)
    return done


def _study(config, paths, *, group=0, trials=1):
    selected = config.part.select_groups(group)[0]
    selected.optuna_settings.execution.trials = trials
    study = create_study(config, selected, paths.study_dir("XX", group) / "study.db")

    def runner(parameters, split, trial):
        del parameters, split
        checkpoint = paths.study_dir("XX", group) / f"trial_{trial.number}.ckpt"
        torch.save({"state_dict": {}}, checkpoint)
        return TrialOutcome([0.2 + trial.number / 10], [0.1, 0.2], checkpoint)

    return selected, run_search(
        selected,
        split_by_source(
            load_preparation_manifest(
                paths.prepared_train("XX", group),
                model="XX",
                group=group,
                allowed_split_ids=set(selected.range_ids),
                fingerprint=preparation_fingerprint(config, group=selected),
            ),
            paths.prepared_train("XX", group),
        ),
        study,
        runner,
    )


def test_group_req_022_s01(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = _project(tmp_path, two=True)
    done = _stub_search(monkeypatch, paths)
    _, recorder = _run_cli(monkeypatch, paths)
    assert done == [0, 1]
    assert recorder.groups == [0, 1]


def test_group_req_022_s02(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = _project(tmp_path, two=True)
    other = paths.checkpoint("XX", 0)
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text("old")
    done = _stub_search(monkeypatch, paths)
    _run_cli(monkeypatch, paths, group=1)
    assert done == [1]
    assert other.read_text() == "old"


def test_group_req_022_s03(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = _project(tmp_path)
    _stub_search(monkeypatch, paths)
    with pytest.raises(ValueError, match="available groups"):
        _run_cli(monkeypatch, paths, group=7)


def test_group_req_004_s01(tmp_path: Path) -> None:
    config, paths = _project(tmp_path)
    group = config.part.groups[0]
    manifest = load_preparation_manifest(
        paths.prepared_train("XX", 0),
        model="XX",
        group=0,
        allowed_split_ids={0},
        fingerprint=preparation_fingerprint(config, group=group),
    )
    split = split_by_source(manifest, paths.prepared_train("XX", 0))
    assert set(split.train_sources).isdisjoint(split.validation_sources)
    assert all(
        any(Path(source).stem + "_" in path.name for source in split.train_sources)
        for path in split.train_images
    )


def test_group_req_004_s02(tmp_path: Path) -> None:
    config, paths = _project(tmp_path)
    manifest = load_preparation_manifest(
        paths.prepared_train("XX", 0), model="XX", group=0, allowed_split_ids={0}
    )
    manifest.sources = manifest.sources[:1]
    with pytest.raises(ValueError, match="at least 2"):
        split_by_source(manifest, paths.prepared_train("XX", 0))


def test_group_req_004_s03(tmp_path: Path) -> None:
    config, paths = _project(tmp_path)
    prepared = paths.prepared_train("XX", 0)
    payload = json.loads((prepared / "manifest.json").read_text())
    payload["group"] = 4
    (prepared / "manifest.json").write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="group mismatch"):
        load_preparation_manifest(prepared, model="XX", group=0, allowed_split_ids={0})


def test_group_req_004_s04(tmp_path: Path) -> None:
    config, paths = _project(tmp_path)
    prepared = paths.prepared_train("XX", 0)
    selected = config.part.groups[0]
    config.image_size = 9
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        load_preparation_manifest(
            prepared,
            model="XX",
            group=0,
            allowed_split_ids={0},
            fingerprint=preparation_fingerprint(config, group=selected),
        )


def test_group_req_005_s01(tmp_path: Path) -> None:
    config, paths = _project(tmp_path)
    selected, (study, outcomes) = _study(config, paths, trials=2)
    assert len(study.trials) == 2
    assert all(item.state == optuna.trial.TrialState.COMPLETE for item in study.trials)
    assert study.best_trial.number in outcomes
    assert selected.optuna_settings.pruner.name == "MedianPruner"


def test_group_req_005_s02(tmp_path: Path) -> None:
    config, paths = _project(tmp_path)
    selected = config.part.groups[0]
    selected.optuna_settings.sampler.seed = 7
    study = create_study(config, selected, paths.study_dir("XX", 0) / "study.db")
    assert study.study_name == "visual-inspection-XX-group-0"


def test_group_req_006_s01(tmp_path: Path) -> None:
    config, paths = _project(tmp_path)
    settings = config.part.groups[0].augmentation.model_copy(deep=True)
    settings.order = ["brightness", "gamma"]
    settings.brightness.probability = 1.0
    settings.brightness.factor_min = settings.brightness.factor_max = 0.5
    settings.gamma.probability = 1.0
    settings.gamma.factor_min = settings.gamma.factor_max = 2.0
    prepared = paths.prepared_train("XX", 0)
    before = {path.name: path.read_bytes() for path in prepared.iterdir()}
    original = paths.original_train("XX") / "a.png"
    original_bytes = original.read_bytes()
    image = np.full((8, 8, 3), 0.8, dtype=np.float32)
    tensor = torch.from_numpy(image.transpose(2, 0, 1).copy())

    augmented = AnomalibTrainingAugmentation(settings).transform(tensor, {})
    assert torch.allclose(augmented, torch.full_like(tensor, 0.16))
    assert np.array_equal(image, np.full_like(image, 0.8))
    assert {path.name: path.read_bytes() for path in prepared.iterdir()} == before
    assert original.read_bytes() == original_bytes

    reversed_settings = settings.model_copy(deep=True)
    reversed_settings.order = ["gamma", "brightness"]
    reversed_result = AugmentationPipeline(reversed_settings)(image, training=True)
    assert np.allclose(reversed_result, 0.32)
    settings.brightness.probability = 0.0
    settings.gamma.probability = 0.0
    assert np.array_equal(AugmentationPipeline(settings)(image, training=True), image)

    settings.order = ["brightness"]
    settings.brightness.probability = 1.0
    settings.brightness.factor_min = 0.5
    settings.brightness.factor_max = 0.8
    first = AugmentationPipeline(settings)(image, training=True)
    second = AugmentationPipeline(settings)(image, training=True)
    assert np.array_equal(first, second)
    assert np.all(first >= image * 0.5)
    assert np.all(first <= image * 0.8)


def test_group_req_006_s02(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config, paths = _project(tmp_path, two=True)
    config.part.groups[1].augmentation.seed = 99
    assert (
        config.part.groups[0].augmentation.seed
        != config.part.groups[1].augmentation.seed
    )
    assert paths.study_dir("XX", 0) != paths.study_dir("XX", 1)
    group = config.part.groups[0]
    prepared = paths.prepared_train("XX", 0)
    manifest = load_preparation_manifest(
        prepared,
        model="XX",
        group=0,
        allowed_split_ids=set(group.range_ids),
        fingerprint=preparation_fingerprint(config, group=group),
    )
    split = split_by_source(manifest, prepared)
    observed: dict[str, Any] = {}

    class FakeFolder:
        def __init__(self, **kwargs):
            observed["folder"] = kwargs

    class FakeEngine:
        def __init__(self, **_kwargs):
            self.trainer = SimpleNamespace(
                save_checkpoint=lambda path: Path(path).write_bytes(b"checkpoint")
            )

        def fit(self, _model, *, datamodule):
            assert isinstance(datamodule, FakeFolder)

        def predict(self, *, model, data_path, return_predictions):
            del model
            assert return_predictions
            observed.setdefault("predicted", []).append(
                [path.read_bytes() for path in Path(data_path).iterdir()]
            )
            return [{"pred_score": [0.2]}]

    monkeypatch.setattr("anomalib.data.Folder", FakeFolder)
    monkeypatch.setattr("anomalib.engine.Engine", FakeEngine)
    monkeypatch.setattr(
        "app.model_training.trainer.create_supersimplenet", lambda **_kwargs: object()
    )
    trial = optuna.create_study().ask()
    runner = AnomalibTrialRunner(
        tmp_path / "trials", DeviceSelection("cpu", "CPU", "test"), group
    )
    outcome = runner(TrialParameters(1.0, 4, 1, ["layer2"], 256), split, trial)
    folder = observed["folder"]
    assert isinstance(folder["train_augmentations"], AnomalibTrainingAugmentation)
    assert folder["val_augmentations"] is None
    assert folder["test_augmentations"] is None
    assert observed["predicted"][0] == [
        path.read_bytes() for path in split.validation_images
    ]
    assert outcome.validation_scores == [0.2]
    image = np.full((8, 8, 3), 0.5, dtype=np.float32)
    assert np.array_equal(
        AugmentationPipeline(group.augmentation)(image, training=False), image
    )


def test_group_req_007_s01(tmp_path: Path) -> None:
    config, paths = _project(tmp_path)
    selected, (study, outcomes) = _study(config, paths)
    split = split_by_source(
        load_preparation_manifest(
            paths.prepared_train("XX", 0), model="XX", group=0, allowed_split_ids={0}
        ),
        paths.prepared_train("XX", 0),
    )
    best = persist_best_trial(
        config=config,
        group=selected,
        paths=paths,
        split=split,
        study=study,
        outcomes=outcomes,
    )
    assert best.group == 0 and best.range_ids == [0]
    assert paths.checkpoint("XX", 0).exists()
    assert (
        load_config(tmp_path, "XX").part.groups[0].optuna_settings.threshold.value
        == best.threshold
    )


def test_group_req_007_s02(tmp_path: Path) -> None:
    config, paths = _project(tmp_path, two=True)
    assert paths.checkpoint("XX", 0) != paths.checkpoint("XX", 1)
    assert paths.study_dir("XX", 0) != paths.study_dir("XX", 1)
    assert config.part.groups[1].id == 1


def test_group_req_007_s03(tmp_path: Path) -> None:
    config, paths = _project(tmp_path, two=True)
    from app.common.config import write_threshold

    write_threshold(paths.model_config("XX"), 0.3, group=1)
    updated = load_config(tmp_path, "XX")
    assert updated.part.groups[0].optuna_settings.threshold.value is None
    assert updated.part.groups[1].optuna_settings.threshold.value == 0.3


def test_group_req_007_s04(tmp_path: Path) -> None:
    config, paths = _project(tmp_path)
    selected, (study, outcomes) = _study(config, paths)
    split = split_by_source(
        load_preparation_manifest(
            paths.prepared_train("XX", 0), model="XX", group=0, allowed_split_ids={0}
        ),
        paths.prepared_train("XX", 0),
    )
    best = persist_best_trial(
        config=config,
        group=selected,
        paths=paths,
        split=split,
        study=study,
        outcomes=outcomes,
    )
    from app.model_evaluation.evaluation import validate_best_trial_contract

    validate_best_trial_contract(
        load_config(tmp_path, "XX"),
        load_config(tmp_path, "XX").part.groups[0],
        paths,
        best,
    )


def test_group_req_007_s05(tmp_path: Path) -> None:
    config, paths = _project(tmp_path)
    from app.common.config import write_threshold

    write_threshold(paths.model_config("XX"), 0.7, group=0)
    assert (
        load_config(tmp_path, "XX").part.groups[0].optuna_settings.threshold.value
        == 0.7
    )


def test_group_req_008_s01(tmp_path: Path) -> None:
    config, paths = _project(tmp_path)
    selected, (first_study, _) = _study(config, paths, trials=1)
    assert [trial.number for trial in first_study.trials] == [0]
    selected.optuna_settings.execution.trials = 3
    resumed = create_study(config, selected, paths.study_dir("XX", 0) / "study.db")
    assert [trial.number for trial in resumed.trials] == [0]
    manifest = load_preparation_manifest(
        paths.prepared_train("XX", 0),
        model="XX",
        group=0,
        allowed_split_ids=set(selected.range_ids),
        fingerprint=preparation_fingerprint(config, group=selected),
    )
    split = split_by_source(manifest, paths.prepared_train("XX", 0))
    executed: list[int] = []

    def runner(parameters, split, trial):
        del parameters, split
        executed.append(trial.number)
        checkpoint = paths.study_dir("XX", 0) / f"trial_{trial.number}.ckpt"
        torch.save({"state_dict": {}}, checkpoint)
        return TrialOutcome([0.2 + trial.number / 10], [0.1, 0.2], checkpoint)

    run_search(selected, split, resumed, runner)
    assert executed == [1, 2]
    assert [trial.number for trial in resumed.trials] == [0, 1, 2]


def test_group_req_008_s02(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = _project(tmp_path, two=True)
    for group in (0, 1):
        checkpoint = paths.checkpoint("XX", group)
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text(f"old group {group}")
        study = paths.study_dir("XX", group) / "old-study.txt"
        study.parent.mkdir(parents=True, exist_ok=True)
        study.write_text("old")
    config_before = paths.model_config("XX").read_bytes()
    _stub_search(monkeypatch, paths)
    _run_cli(monkeypatch, paths, group=1, restart=True)
    assert paths.checkpoint("XX", 0).read_text() == "old group 0"
    assert (paths.study_dir("XX", 0) / "old-study.txt").read_text() == "old"
    assert paths.checkpoint("XX", 1).read_text() == "group 1"
    assert not (paths.study_dir("XX", 1) / "old-study.txt").exists()
    assert paths.model_config("XX").read_bytes() == config_before


def test_group_req_008_s03(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = _project(tmp_path, two=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "app.common.cli.select_device",
        lambda: DeviceSelection("cpu", "CPU", "test"),
    )
    done = _stub_search(monkeypatch, paths, fail_group=1)
    with pytest.raises(typer.Exit) as error:
        training_cli._train_command(model="XX", group=None, restart=False)
    assert error.value.exit_code == 3
    assert done == [0]
    first_checkpoint = paths.checkpoint("XX", 0).read_bytes()
    assert not paths.checkpoint("XX", 1).exists()

    retried = _stub_search(monkeypatch, paths)
    training_cli._train_command(model="XX", group=None, restart=False)
    assert retried == [0, 1]
    assert paths.checkpoint("XX", 0).read_bytes() == first_checkpoint
    assert paths.checkpoint("XX", 1).is_file()
