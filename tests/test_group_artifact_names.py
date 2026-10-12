from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch
from group_evaluation_helpers import FakePredictor, aligned, project, recorder
from optuna.trial import Trial

from app.common.config import load_config
from app.common.paths import ProjectPaths
from app.common.result_index import publish_current, read_current
from app.common.runtime import DeviceSelection, RunRecorder
from app.image_preparation.preparation import prepare_training
from app.model_evaluation import cli as evaluation_cli
from app.model_training import cli as training_cli
from app.model_training.search import TrialOutcome


@pytest.mark.parametrize(
    ("group", "name"),
    [(0, "group_00"), (9, "group_09"), (10, "group_10"), (100, "group_100")],
)
def test_preparation_group_names(tmp_path: Path, group: int, name: str) -> None:
    paths = ProjectPaths(tmp_path)
    assert paths.check_image("XX", group).name == f"{name}.png"
    assert paths.prepared_train("XX", group).name == name
    assert paths.group_name(group) == name


@pytest.mark.parametrize(
    ("group", "name"),
    [(0, "group_00"), (9, "group_09"), (10, "group_10"), (100, "group_100")],
)
def test_training_group_names(tmp_path: Path, group: int, name: str) -> None:
    paths = ProjectPaths(tmp_path)
    assert paths.study_dir("XX", group).name == name
    assert paths.checkpoint("XX", group).name == f"{name}.ckpt"


def test_legacy_training_artifacts_are_not_used(tmp_path: Path) -> None:
    paths = ProjectPaths(tmp_path)
    legacy_study = tmp_path / "optuna" / "XX" / "group_0"
    legacy_study.mkdir(parents=True)
    legacy_checkpoint = tmp_path / "weights" / "XX" / "group_0.ckpt"
    legacy_checkpoint.parent.mkdir(parents=True)
    legacy_checkpoint.write_bytes(b"old")
    assert not (paths.study_dir("XX", 0) / "best_trial.json").exists()
    assert not paths.checkpoint("XX", 0).exists()
    assert legacy_study.is_dir()
    assert legacy_checkpoint.read_bytes() == b"old"


def test_result_group_names(tmp_path: Path) -> None:
    paths = ProjectPaths(tmp_path)
    generation = "a" * 32
    expected: dict[int, str] = {}
    for group in (0, 9, 10, 100):
        relative = f"generations/{generation}/{paths.group_name(group)}"
        (paths.results("XX") / relative).mkdir(parents=True)
        expected[group] = relative
    publish_current(paths, "XX", expected)
    assert read_current(paths, "XX", allowed_group_ids=set(expected)) == expected
    payload = json.loads(paths.result_current("XX").read_text())
    assert set(payload["groups"]) == {"0", "9", "10", "100"}


def test_legacy_result_reference_requires_regeneration(tmp_path: Path) -> None:
    paths = ProjectPaths(tmp_path)
    relative = f"generations/{'a' * 32}/group_0"
    (paths.results("XX") / relative).mkdir(parents=True)
    publish_current(paths, "XX", {0: relative})
    with pytest.raises(ValueError, match="invalid current.json path"):
        read_current(paths, "XX", allowed_group_ids={0})
    assert (paths.results("XX") / relative).is_dir()


def test_legacy_artifacts_can_be_regenerated_and_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, paths = project(tmp_path)
    config_path = paths.model_config("XX")
    payload = json.loads(config_path.read_text())
    payload["group_detail"]["0"]["optuna_settings"]["execution"]["trials"] = 1
    config_path.write_text(json.dumps(payload))
    config = load_config(tmp_path, "XX")

    legacy_study = paths.study_dir("XX", 0).with_name("group_0")
    legacy_checkpoint = paths.checkpoint("XX", 0).with_name("group_0.ckpt")
    paths.study_dir("XX", 0).rename(legacy_study)
    paths.checkpoint("XX", 0).rename(legacy_checkpoint)
    old_study = (legacy_study / "best_trial.json").read_bytes()
    old_checkpoint = legacy_checkpoint.read_bytes()

    legacy_result = f"generations/{'a' * 32}/group_0"
    (paths.results("XX") / legacy_result).mkdir(parents=True)
    publish_current(paths, "XX", {0: legacy_result})

    training_run = RunRecorder("train", "XX", DeviceSelection("cpu", "CPU", "test"))
    monkeypatch.setattr(
        training_cli,
        "_run",
        lambda _command, _model, action, **_kwargs: action(paths, training_run),
    )
    with pytest.raises(ValueError, match="group 0 failed"):
        training_cli._train_command(model="XX", group=0)

    prepare_training(config, paths, aligner=aligned)

    class FakeRunner:
        def __init__(self, directory: Path, _device: object, _group: object) -> None:
            self.directory = directory

        def __call__(
            self, _parameters: object, _split: object, trial: Trial
        ) -> TrialOutcome:
            self.directory.mkdir(parents=True, exist_ok=True)
            checkpoint = self.directory / f"trial_{trial.number}.ckpt"
            torch.save({"state_dict": {}}, checkpoint)
            return TrialOutcome([0.2], [0.1, 0.2], checkpoint)

    monkeypatch.setattr(training_cli, "AnomalibTrialRunner", FakeRunner)
    training_cli._train_command(model="XX", group=0)
    assert paths.checkpoint("XX", 0).is_file()
    assert (paths.study_dir("XX", 0) / "best_trial.json").is_file()
    assert (legacy_study / "best_trial.json").read_bytes() == old_study
    assert legacy_checkpoint.read_bytes() == old_checkpoint

    monkeypatch.setattr(
        evaluation_cli,
        "_run",
        lambda _command, _model, action, **_kwargs: action(paths, recorder()),
    )
    monkeypatch.setattr(
        evaluation_cli,
        "CheckpointPredictor",
        lambda *_args, **_kwargs: FakePredictor(score=0.3),
    )
    with pytest.raises(ValueError, match="invalid current.json path"):
        evaluation_cli._test_command(model="XX", group=0)

    evaluation_cli._test_command(model="XX", group=None)
    current = read_current(paths, "XX", allowed_group_ids={0})
    assert current[0].endswith("/group_00")
    result = json.loads(
        (paths.results("XX") / current[0] / "sample.png.json").read_text()
    )
    assert result["group"] == 0
