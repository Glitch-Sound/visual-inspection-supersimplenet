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
    BestTrialResult,
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
    cross_validation_splits,
    run_search,
    split_by_source,
)
from app.model_training.trainer import AnomalibTrialRunner

_real_fit_selected_parameters = training_cli.fit_selected_parameters


def _aligned(
    image: np.ndarray, _reference: np.ndarray, _settings: object
) -> AlignedImage:
    return AlignedImage(image, 20, 0.8)


def _project(
    root: Path,
    *,
    two: bool = False,
    two_splits: bool = False,
    missing_second: bool = False,
):
    ranges = (
        [{"id": 0, "x": 0, "y": 0}, {"id": 1, "x": 8, "y": 0}] if two_splits else None
    )
    blacklist = (
        [{"image": name, "id": [1]} for name in ("base.png", "a.png", "b.png", "c.png")]
        if missing_second
        else None
    )
    config, paths = build_project(root, ranges=ranges, blacklist=blacklist)
    if two:
        path = paths.model_config("XX")
        payload = json.loads(path.read_text())
        second = json.loads(json.dumps(payload["groups"][0]))
        second["id"] = 1
        payload["group_detail"]["1"] = json.loads(
            json.dumps(payload["group_detail"]["0"])
        )
        path.write_text(
            json.dumps({**payload, "groups": [payload["groups"][0], second]})
        )
        config = load_config(root, "XX")
    for name in ("base.png", "a.png", "b.png", "c.png"):
        write_test_image(paths.original_train("XX") / name)
    prepare_training(config, paths, aligner=_aligned)
    return config, paths


def _run_cli(monkeypatch: pytest.MonkeyPatch, paths, *, group=None, restart=False):
    if training_cli.fit_selected_parameters is _real_fit_selected_parameters:

        def fake_selected(_parameters, *, validation_images, work_dir, **_kwargs):
            work_dir.mkdir(parents=True, exist_ok=True)
            checkpoint = work_dir / "model.ckpt"
            torch.save({"state_dict": {}}, checkpoint)
            return checkpoint, [0.2] * len(validation_images)

        monkeypatch.setattr(training_cli, "fit_selected_parameters", fake_selected)
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

    def fake_selected(_parameters, *, validation_images, work_dir, **_kwargs):
        work_dir.mkdir(parents=True, exist_ok=True)
        checkpoint = work_dir / "model.ckpt"
        torch.save({"state_dict": {}}, checkpoint)
        return checkpoint, [0.2] * len(validation_images)

    monkeypatch.setattr(training_cli, "fit_selected_parameters", fake_selected)

    class Study:
        trials = []
        best_trial = SimpleNamespace(
            params={
                "learning_rate_multiplier": 1.0,
                "batch_size": 4,
                "epochs": 1,
                "feature_layers": '["layer2"]',
                "image_size": 256,
            }
        )

    monkeypatch.setattr("app.model_training.cli.create_study", lambda *_args: Study())
    monkeypatch.setattr(
        "app.model_training.cli.run_search",
        lambda group, _split, study, _runner, **_kw: (study, {}),
    )
    monkeypatch.setattr(
        "app.model_training.cli.show_trial_conditions", lambda *_args: None
    )

    def persist(*, config, group, paths, split, study, outcomes, **_kwargs):
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


def _synthetic_study(config, paths, values: list[tuple[float, float]]):
    selected = config.part.groups[0]
    selected.optuna_settings.objective = "synthetic_auroc"
    selected.optuna_settings.execution.trials = len(values)
    study = create_study(config, selected, paths.study_dir("XX", 0) / "study.db")
    split = split_by_source(
        load_preparation_manifest(
            paths.prepared_train("XX", 0), model="XX", group=0, allowed_split_ids={0}
        ),
        paths.prepared_train("XX", 0),
    )

    def runner(parameters, split, trial):
        del parameters, split
        normal, synthetic = values[trial.number]
        checkpoint = paths.study_dir("XX", 0) / f"trial_{trial.number}.ckpt"
        torch.save({"state_dict": {}}, checkpoint)
        return TrialOutcome([normal], [0.1, 0.2], checkpoint, [synthetic])

    study, outcomes = run_search(selected, split, study, runner)
    return selected, split, study, outcomes


def _oof_project(
    root: Path,
    *,
    two: bool = False,
    two_splits: bool = False,
    missing_second: bool = False,
):
    _, paths = _project(
        root, two=two, two_splits=two_splits, missing_second=missing_second
    )
    payload = json.loads(paths.model_config("XX").read_text())
    for detail in payload["group_detail"].values():
        threshold = detail["optuna_settings"]["threshold"]
        threshold.update(
            method="out_of_fold_percentile", folds=2, percentile=50, margin=0.05
        )
        detail["optuna_settings"]["execution"]["trials"] = 1
    paths.model_config("XX").write_text(json.dumps(payload))
    return load_config(root, "XX"), paths


def _split_oof_project(root: Path, *, minimum: int, missing_second: bool = False):
    _, paths = _oof_project(root, two_splits=True, missing_second=missing_second)
    payload = json.loads(paths.model_config("XX").read_text())
    payload["group_detail"]["0"]["optuna_settings"]["threshold"].update(
        unit="split", min_score_count=minimum
    )
    paths.model_config("XX").write_text(json.dumps(payload))
    return load_config(root, "XX"), paths


def test_split_threshold_calculation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = _split_oof_project(tmp_path, minimum=4)
    _fake_oof_training(monkeypatch)
    _run_cli(monkeypatch, paths, group=0)
    best = BestTrialResult.read_json(paths.study_dir("XX", 0) / "best_trial.json")
    assert set(best.split_thresholds) == {"0", "1"}
    for split_id, item in best.split_thresholds.items():
        scores = [
            score.score
            for score in best.score_by_source
            if score.split_image.endswith(f"_{int(split_id):02d}.png")
        ]
        assert item.score_count == len(scores) == 4
        assert item.source == "calculated"
        assert item.value == pytest.approx(min(1.0, np.percentile(scores, 50) + 0.05))
    assert best.threshold == pytest.approx(
        min(
            1.0, np.percentile([item.score for item in best.score_by_source], 50) + 0.05
        )
    )
    config = load_config(tmp_path, "XX")
    assert (
        config.part.groups[0].optuna_settings.threshold.split_values
        == best.split_thresholds
    )
    metadata = torch.load(paths.checkpoint("XX", 0), weights_only=False)[
        "visual_inspection"
    ]
    assert metadata["split_thresholds"] == {
        key: item.model_dump() for key, item in best.split_thresholds.items()
    }


def test_split_threshold_fallback_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = _split_oof_project(tmp_path, minimum=3, missing_second=True)
    _fake_oof_training(monkeypatch)
    _, recorder = _run_cli(monkeypatch, paths, group=0)
    best = BestTrialResult.read_json(paths.study_dir("XX", 0) / "best_trial.json")
    assert len(best.threshold_warnings) == 1
    assert recorder.warnings == best.threshold_warnings
    assert best.split_thresholds["0"].source == "calculated"
    fallback = best.split_thresholds["1"]
    assert fallback.value == best.threshold
    assert fallback.source == "group_fallback"
    assert fallback.score_count == 0
    assert "split 1" in best.threshold_warnings[0]
    assert "score count 0" in best.threshold_warnings[0]
    assert "min_score_count 3" in best.threshold_warnings[0]


def test_group_threshold_default_compatibility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = _oof_project(tmp_path)
    _fake_oof_training(monkeypatch)
    _run_cli(monkeypatch, paths, group=0)
    best = BestTrialResult.read_json(paths.study_dir("XX", 0) / "best_trial.json")
    assert best.threshold_unit == "group"
    assert best.split_thresholds == {}
    assert best.threshold == pytest.approx(
        min(
            1.0, np.percentile([item.score for item in best.score_by_source], 50) + 0.05
        )
    )


def test_split_threshold_count_change_requires_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = _split_oof_project(tmp_path, minimum=3)
    _fake_oof_training(monkeypatch)
    _run_cli(monkeypatch, paths, group=0)
    path = paths.model_config("XX")
    payload = json.loads(path.read_text())
    payload["group_detail"]["0"]["optuna_settings"]["threshold"]["min_score_count"] = 5
    path.write_text(json.dumps(payload))
    load_config(tmp_path, "XX")
    with pytest.raises(ValueError, match="train --restart"):
        _run_cli(monkeypatch, paths, group=0)
    _run_cli(monkeypatch, paths, group=0, restart=True)
    best = BestTrialResult.read_json(paths.study_dir("XX", 0) / "best_trial.json")
    assert best.min_score_count == 5
    assert all(
        item.source == "group_fallback" for item in best.split_thresholds.values()
    )


def _fake_oof_training(monkeypatch: pytest.MonkeyPatch):
    calls = []

    class FakeRunner:
        def __init__(self, work_dir, _device, _group):
            self.work_dir = work_dir

        def __call__(self, _parameters, _split, trial):
            self.work_dir.mkdir(parents=True, exist_ok=True)
            checkpoint = self.work_dir / f"trial-{trial.number}.ckpt"
            torch.save({"state_dict": {"source": "search"}}, checkpoint)
            return TrialOutcome([0.2], [0.1, 0.2], checkpoint)

    def fit(parameters, *, train_images, validation_images, work_dir, **_kwargs):
        calls.append(
            (parameters, tuple(train_images), tuple(validation_images), work_dir)
        )
        work_dir.mkdir(parents=True, exist_ok=True)
        checkpoint = work_dir / "model.ckpt"
        torch.save({"state_dict": {"source": work_dir.name}}, checkpoint)
        return checkpoint, [
            0.2 + 0.1 * index for index in range(len(validation_images))
        ]

    monkeypatch.setattr(training_cli, "AnomalibTrialRunner", FakeRunner)
    monkeypatch.setattr(training_cli, "fit_selected_parameters", fit)
    return calls


def test_oof_folds_cover_sources_without_leakage(tmp_path: Path) -> None:
    config, paths = _project(tmp_path)
    selected = config.part.groups[0]
    manifest = load_preparation_manifest(
        paths.prepared_train("XX", 0), model="XX", group=0, allowed_split_ids={0}
    )
    folds = cross_validation_splits(
        manifest, paths.prepared_train("XX", 0), folds=2, seed=42
    )
    all_sources = {item.source_image for item in manifest.sources if item.splits}
    assert len(folds) == 2
    assert sorted(name for fold in folds for name in fold.validation_sources) == sorted(
        all_sources
    )
    for fold in folds:
        assert set(fold.train_sources).isdisjoint(fold.validation_sources)
        assert set(fold.train_sources) | set(fold.validation_sources) == all_sources
        assert len(fold.validation_images) == len(fold.validation_sources)
    assert selected.optuna_settings.normal_only.train_ratio == 0.8


def test_leave_one_out_uses_each_source_once(tmp_path: Path) -> None:
    _, paths = _project(tmp_path)
    manifest = load_preparation_manifest(
        paths.prepared_train("XX", 0), model="XX", group=0, allowed_split_ids={0}
    )
    folds = cross_validation_splits(
        manifest, paths.prepared_train("XX", 0), folds="leave_one_out", seed=42
    )
    assert len(folds) == 4
    assert all(len(fold.validation_sources) == 1 for fold in folds)
    assert len({fold.validation_sources[0] for fold in folds}) == 4


def test_oof_rejects_invalid_fold_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = _oof_project(tmp_path)
    path = paths.model_config("XX")
    payload = json.loads(path.read_text())
    payload["group_detail"]["0"]["optuna_settings"]["threshold"]["folds"] = 5
    path.write_text(json.dumps(payload))
    old_checkpoint = paths.checkpoint("XX", 0)
    old_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    old_checkpoint.write_bytes(b"old")
    _fake_oof_training(monkeypatch)
    with pytest.raises(ValueError, match="source count is 4"):
        _run_cli(monkeypatch, paths, group=0)
    assert old_checkpoint.read_bytes() == b"old"
    for invalid in (1, 0):
        payload["group_detail"]["0"]["optuna_settings"]["threshold"]["folds"] = invalid
        path.write_text(json.dumps(payload))
        with pytest.raises(ValueError, match="folds"):
            load_config(tmp_path, "XX")


def test_oof_threshold_and_score_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = _oof_project(tmp_path)
    calls = _fake_oof_training(monkeypatch)
    _run_cli(monkeypatch, paths, group=0)
    best = BestTrialResult.read_json(paths.study_dir("XX", 0) / "best_trial.json")
    scores = [item.score for item in best.score_by_source]
    assert best.threshold == pytest.approx(min(1.0, np.percentile(scores, 50) + 0.05))
    assert best.threshold_method == "out_of_fold_percentile"
    assert best.threshold_margin == 0.05
    assert len(best.cross_validation) == 2
    assert {item.source_image for item in best.score_by_source} == set(
        best.final_train_sources
    )
    assert all(item.split_image.endswith(".png") for item in best.score_by_source)
    assert len(calls) == 3


def test_oof_invalid_scores_preserve_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = _oof_project(tmp_path)
    _fake_oof_training(monkeypatch)
    _run_cli(monkeypatch, paths, group=0)
    checkpoint = paths.checkpoint("XX", 0)
    best = paths.study_dir("XX", 0) / "best_trial.json"
    before = (
        checkpoint.read_bytes(),
        best.read_bytes(),
        paths.model_config("XX").read_bytes(),
    )

    def bad_fit(parameters, *, validation_images, work_dir, **_kwargs):
        del parameters
        work_dir.mkdir(parents=True, exist_ok=True)
        target = work_dir / "model.ckpt"
        torch.save({"state_dict": {}}, target)
        return target, [float("nan")] * len(validation_images)

    monkeypatch.setattr(training_cli, "fit_selected_parameters", bad_fit)
    with pytest.raises(RuntimeError, match="cross-validation fold 1 failed"):
        _run_cli(monkeypatch, paths, group=0, restart=True)
    assert (
        checkpoint.read_bytes(),
        best.read_bytes(),
        paths.model_config("XX").read_bytes(),
    ) == before


def test_oof_final_refit_uses_all_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = _oof_project(tmp_path)
    calls = _fake_oof_training(monkeypatch)
    _run_cli(monkeypatch, paths, group=0)
    best = BestTrialResult.read_json(paths.study_dir("XX", 0) / "best_trial.json")
    assert best.final_train_sources == ["a.png", "b.png", "base.png", "c.png"]
    assert len(calls[-1][1]) == 4
    assert calls[-1][1] == calls[-1][2]
    assert (
        torch.load(paths.checkpoint("XX", 0), weights_only=False)["state_dict"][
            "source"
        ]
        == "final_refit"
    )


def test_legacy_threshold_with_full_refit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = _project(tmp_path)
    payload = json.loads(paths.model_config("XX").read_text())
    payload["group_detail"]["0"]["optuna_settings"]["execution"]["trials"] = 1
    paths.model_config("XX").write_text(json.dumps(payload))
    calls = _fake_oof_training(monkeypatch)
    _run_cli(monkeypatch, paths, group=0)
    best = BestTrialResult.read_json(paths.study_dir("XX", 0) / "best_trial.json")
    assert best.threshold_method == "training_percentile"
    assert best.threshold == pytest.approx(0.199)
    assert len(calls) == 1 and len(calls[0][1]) == 4
    assert len(best.final_train_sources) == 4


def test_refit_failure_preserves_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = _oof_project(tmp_path)
    _fake_oof_training(monkeypatch)
    _run_cli(monkeypatch, paths, group=0)
    checkpoint = paths.checkpoint("XX", 0)
    best = paths.study_dir("XX", 0) / "best_trial.json"
    before = (
        checkpoint.read_bytes(),
        best.read_bytes(),
        paths.model_config("XX").read_bytes(),
    )

    def fail_final(parameters, *, train_images, validation_images, work_dir, **_kwargs):
        del parameters, train_images
        if work_dir.name == "final_refit":
            raise RuntimeError("final fit failed")
        work_dir.mkdir(parents=True, exist_ok=True)
        target = work_dir / "model.ckpt"
        torch.save({"state_dict": {}}, target)
        return target, [0.2] * len(validation_images)

    monkeypatch.setattr(training_cli, "fit_selected_parameters", fail_final)
    with pytest.raises(RuntimeError, match="final fit failed"):
        _run_cli(monkeypatch, paths, group=0, restart=True)
    assert (
        checkpoint.read_bytes(),
        best.read_bytes(),
        paths.model_config("XX").read_bytes(),
    ) == before


def test_final_artifact_threshold_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.model_evaluation.evaluation import validate_best_trial_contract
    from app.model_evaluation.predictor import load_checkpoint_metadata

    _, paths = _oof_project(tmp_path)
    _fake_oof_training(monkeypatch)
    _run_cli(monkeypatch, paths, group=0)
    config = load_config(tmp_path, "XX")
    group = config.part.groups[0]
    best = BestTrialResult.read_json(paths.study_dir("XX", 0) / "best_trial.json")
    metadata = load_checkpoint_metadata(paths.checkpoint("XX", 0))
    assert (
        best.threshold == group.optuna_settings.threshold.value == metadata["threshold"]
    )
    validate_best_trial_contract(config, group, paths, best)


def test_training_reuses_pretrained_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import timm.models._hub as hub
    from timm.models.resnet import ResNet

    from app.common.model_adapter import create_supersimplenet

    cache = tmp_path / "model.bin"
    downloads = []

    def cached_download(_repo_id, *, filename, **_kwargs):
        assert filename == "pytorch_model.bin"
        if not cache.exists():
            cache.write_bytes(b"cached")
            downloads.append(cache)
        return str(cache)

    monkeypatch.setattr(hub, "_has_safetensors", False)
    monkeypatch.setattr(hub, "hf_hub_download", cached_download)
    monkeypatch.setattr(hub, "_torch_load", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        ResNet,
        "load_state_dict",
        lambda *_args, **_kwargs: SimpleNamespace(missing_keys=[], unexpected_keys=[]),
    )
    for _ in range(2):
        create_supersimplenet(
            layers=["layer2"], image_size=256, learning_rate_multiplier=1.0
        )
    assert downloads == [cache]


def test_refit_artifact_transaction_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.common.artifact_transaction import recover_artifact_transaction
    from app.model_training import artifacts as artifact_module

    _, paths = _oof_project(tmp_path)
    _fake_oof_training(monkeypatch)
    _run_cli(monkeypatch, paths, group=0)
    checkpoint = paths.checkpoint("XX", 0)
    best = paths.study_dir("XX", 0) / "best_trial.json"
    previous = (
        checkpoint.read_bytes(),
        best.read_bytes(),
        paths.model_config("XX").read_bytes(),
    )
    original = artifact_module._replace_staged_artifact
    calls = 0

    def fail_second(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("interrupted update")
        original(source, target)

    monkeypatch.setattr(artifact_module, "_replace_staged_artifact", fail_second)
    with pytest.raises(RuntimeError, match="interrupted update"):
        _run_cli(monkeypatch, paths, group=0, restart=True)
    recover_artifact_transaction(paths, "XX", 0)
    assert (
        checkpoint.read_bytes(),
        best.read_bytes(),
        paths.model_config("XX").read_bytes(),
    ) == previous


def test_interrupted_restart_restores_old_artifacts_before_next_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.common.cli import _run
    from app.model_training.artifacts import restart_training

    _, paths = build_project(tmp_path)
    study_dir = paths.study_dir("XX", 0)
    study_dir.mkdir(parents=True)
    (study_dir / "best_trial.json").write_bytes(b"old best")
    checkpoint = paths.checkpoint("XX", 0)
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"old checkpoint")
    old_config = paths.model_config("XX").read_bytes()
    backup = restart_training(paths, "XX", 0)
    assert backup is not None
    study_dir.mkdir()
    (study_dir / "study.db").write_bytes(b"interrupted search")

    monkeypatch.chdir(tmp_path)
    _run("test", "XX", lambda _paths, _recorder: None)

    assert (study_dir / "best_trial.json").read_bytes() == b"old best"
    assert not (study_dir / "study.db").exists()
    assert checkpoint.read_bytes() == b"old checkpoint"
    assert paths.model_config("XX").read_bytes() == old_config
    assert not backup.exists()


def test_process_interruption_during_restart_update_recovers_old_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.common.cli import _run
    from app.model_training import artifacts as artifact_module

    _, paths = _oof_project(tmp_path)
    _fake_oof_training(monkeypatch)
    _run_cli(monkeypatch, paths, group=0)
    checkpoint = paths.checkpoint("XX", 0)
    best = paths.study_dir("XX", 0) / "best_trial.json"
    previous = (
        checkpoint.read_bytes(),
        best.read_bytes(),
        paths.model_config("XX").read_bytes(),
    )
    original_replace = artifact_module._replace_staged_artifact
    calls = 0

    def interrupt_second(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt("simulated process interruption")
        original_replace(source, target)

    monkeypatch.setattr(artifact_module, "_replace_staged_artifact", interrupt_second)
    with pytest.raises(KeyboardInterrupt, match="simulated process interruption"):
        _run_cli(monkeypatch, paths, group=0, restart=True)
    assert (paths.study_dir("XX", 0) / ".artifact-transaction.json").exists()

    monkeypatch.chdir(tmp_path)
    _run("test", "XX", lambda _paths, _recorder: None)

    assert (
        checkpoint.read_bytes(),
        best.read_bytes(),
        paths.model_config("XX").read_bytes(),
    ) == previous
    study_dir = paths.study_dir("XX", 0)
    assert not study_dir.with_name(study_dir.name + ".restart-backup").exists()


def test_interrupted_restart_after_publication_keeps_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.common.cli import _run
    from app.model_training.artifacts import restart_training

    _, paths = build_project(tmp_path)
    study_dir = paths.study_dir("XX", 0)
    study_dir.mkdir(parents=True)
    (study_dir / "best_trial.json").write_bytes(b"same best")
    backup = restart_training(paths, "XX", 0)
    assert backup is not None
    study_dir.mkdir()
    (study_dir / "best_trial.json").write_bytes(b"same best")
    (study_dir / "study.db").write_bytes(b"replacement history")

    monkeypatch.chdir(tmp_path)
    _run("test", "XX", lambda _paths, _recorder: None)

    assert (study_dir / "study.db").read_bytes() == b"replacement history"
    assert not backup.exists()


def test_refit_contract_mismatch_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.model_evaluation.evaluation import validate_best_trial_contract

    _, paths = _oof_project(tmp_path)
    _fake_oof_training(monkeypatch)
    _run_cli(monkeypatch, paths, group=0)
    config = load_config(tmp_path, "XX")
    group = config.part.groups[0]
    best = BestTrialResult.read_json(paths.study_dir("XX", 0) / "best_trial.json")
    group.optuna_settings.threshold.margin = 0.07
    with pytest.raises(ValueError, match="margin"):
        validate_best_trial_contract(config, group, paths, best)


def test_refit_group_thresholds_are_independent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = _oof_project(tmp_path, two=True)
    _fake_oof_training(monkeypatch)
    _run_cli(monkeypatch, paths, group=0)
    first = BestTrialResult.read_json(paths.study_dir("XX", 0) / "best_trial.json")
    first_checkpoint = paths.checkpoint("XX", 0).read_bytes()
    payload = json.loads(paths.model_config("XX").read_text())
    payload["group_detail"]["1"]["optuna_settings"]["threshold"]["margin"] = 0.1
    paths.model_config("XX").write_text(json.dumps(payload))
    _run_cli(monkeypatch, paths, group=1)
    config = load_config(tmp_path, "XX")
    second = BestTrialResult.read_json(paths.study_dir("XX", 1) / "best_trial.json")
    assert second.threshold != first.threshold
    assert config.part.groups[0].optuna_settings.threshold.value == first.threshold
    assert paths.checkpoint("XX", 0).read_bytes() == first_checkpoint


def test_req_031_s01(tmp_path: Path) -> None:
    config, paths = _project(tmp_path)
    selected, (study, _) = _study(config, paths, trials=1)
    selected.optuna_settings.execution.trials = 2
    resumed = create_study(config, selected, paths.study_dir("XX", 0) / "study.db")
    assert len(resumed.trials) == len(study.trials) == 1


def test_legacy_normal_study_resumes_without_evaluation_contract(
    tmp_path: Path,
) -> None:
    config, paths = _project(tmp_path)
    selected = config.part.groups[0]
    storage = paths.study_dir("XX", 0) / "study.db"
    storage.parent.mkdir(parents=True)
    legacy = optuna.create_study(
        study_name="visual-inspection-XX-group-0",
        storage=f"sqlite:///{storage}",
        direction="minimize",
    )
    legacy.add_trial(optuna.create_trial(value=0.2, params={}, distributions={}))
    resumed = create_study(config, selected, storage)
    assert len(resumed.trials) == 1
    assert resumed.user_attrs["evaluation_contract"]["objective"] == "normal_percentile"


def test_req_031_s02(tmp_path: Path) -> None:
    config, paths = _project(tmp_path)
    selected, _ = _study(config, paths, trials=1)
    checkpoint = paths.checkpoint("XX", 0)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_bytes(b"existing")
    selected.optuna_settings.objective = "synthetic_auroc"
    with pytest.raises(ValueError, match="train --restart"):
        create_study(config, selected, paths.study_dir("XX", 0) / "study.db")
    assert checkpoint.read_bytes() == b"existing"


def test_req_032_s01(tmp_path: Path) -> None:
    from app.model_training.search import synthetic_auroc

    for normal, synthetic in (([], [0.5]), ([0.5], []), ([float("nan")], [0.5])):
        with pytest.raises(ValueError, match="finite"):
            synthetic_auroc(normal, synthetic)

    config, paths = _project(tmp_path)
    selected = config.part.groups[0]
    selected.optuna_settings.objective = "synthetic_auroc"
    selected.optuna_settings.execution.trials = 1
    study = create_study(config, selected, paths.study_dir("XX", 0) / "study.db")
    split = split_by_source(
        load_preparation_manifest(
            paths.prepared_train("XX", 0), model="XX", group=0, allowed_split_ids={0}
        ),
        paths.prepared_train("XX", 0),
    )
    old_checkpoint = paths.checkpoint("XX", 0)
    old_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    old_checkpoint.write_bytes(b"existing")

    def invalid_runner(parameters, split, trial):
        del parameters, split, trial
        return TrialOutcome([0.2], [0.1], old_checkpoint, [float("nan")])

    with pytest.raises(RuntimeError, match="all Optuna trials failed"):
        run_search(selected, split, study, invalid_runner)
    assert study.trials[0].state == optuna.trial.TrialState.FAIL
    assert "finite" in study.trials[0].user_attrs["failure_reason"]
    assert old_checkpoint.read_bytes() == b"existing"


def test_generation_failure_is_recorded_as_failed_trial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = _project(tmp_path)
    config_path = paths.model_config("XX")
    payload = json.loads(config_path.read_text())
    payload["group_detail"]["0"]["optuna_settings"]["objective"] = "synthetic_auroc"
    config_path.write_text(json.dumps(payload))
    old_config = config_path.read_bytes()
    old_checkpoint = paths.checkpoint("XX", 0)
    old_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    old_checkpoint.write_bytes(b"existing")
    old_best = paths.study_dir("XX", 0) / "best_trial.json"
    old_best.parent.mkdir(parents=True, exist_ok=True)
    old_best.write_text("existing")

    def fail_generation(*args, **kwargs):
        del args, kwargs
        raise ValueError("invalid validation image")

    monkeypatch.setattr(training_cli, "create_synthetic_validation", fail_generation)
    with pytest.raises(RuntimeError, match="all Optuna trials failed"):
        _run_cli(monkeypatch, paths, group=0)

    config = load_config(tmp_path, "XX")
    selected = config.part.groups[0]
    study = create_study(config, selected, paths.study_dir("XX", 0) / "study.db")
    assert len(study.trials) == 1
    assert study.trials[0].state == optuna.trial.TrialState.FAIL
    assert "invalid validation image" in study.trials[0].user_attrs["failure_reason"]
    assert old_checkpoint.read_bytes() == b"existing"
    assert old_best.read_text() == "existing"
    assert config_path.read_bytes() == old_config

    selected.optuna_settings.execution.trials = 2
    split = split_by_source(
        load_preparation_manifest(
            paths.prepared_train("XX", 0), model="XX", group=0, allowed_split_ids={0}
        ),
        paths.prepared_train("XX", 0),
    )

    def recovered_runner(parameters, split, trial):
        del parameters, split, trial
        return TrialOutcome([0.2], [0.1], old_checkpoint, [0.8])

    resumed, _ = run_search(selected, split, study, recovered_runner)
    assert resumed.best_trial.number == 1


def test_req_005_s01_synthetic(tmp_path: Path) -> None:
    config, paths = _project(tmp_path)
    _, _, study, _ = _synthetic_study(config, paths, [(0.1, 0.1), (0.4, 0.8)])
    assert study.direction == optuna.study.StudyDirection.MAXIMIZE
    assert study.best_trial.number == 1
    assert study.trials[0].value == 0.5
    assert study.trials[1].value == 1.0


def test_req_005_s02_synthetic(tmp_path: Path) -> None:
    config, paths = _project(tmp_path)
    selected, split, study, outcomes = _synthetic_study(config, paths, [(0.2, 0.8)])
    best = persist_best_trial(
        config=config,
        group=selected,
        paths=paths,
        split=split,
        study=study,
        outcomes=outcomes,
    )
    summary = training_cli.format_training_summary(best)
    assert "擬似AUROC暫定探索指標=" in summary
    assert "精度" not in summary and "再現率" not in summary


def test_synthetic_validation_is_reused_across_trials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _, paths = _project(tmp_path)
    config_path = paths.model_config("XX")
    payload = json.loads(config_path.read_text())
    payload["group_detail"]["0"]["optuna_settings"]["objective"] = "synthetic_auroc"
    config_path.write_text(json.dumps(payload))
    observed: list[tuple[Path, ...]] = []
    original = training_cli.create_synthetic_validation

    def record(images, destination, *, group, settings):
        generated = original(images, destination, group=group, settings=settings)
        observed.append(generated)
        return generated

    monkeypatch.setattr(training_cli, "create_synthetic_validation", record)
    _stub_search(monkeypatch, paths)
    _run_cli(monkeypatch, paths, group=0)
    assert len(observed) == 1
    assert len(observed[0]) > 0
    assert "目的=synthetic_auroc" in capsys.readouterr().err
    assert not observed[0][0].exists()


def test_req_005_s03(tmp_path: Path) -> None:
    config, paths = _project(tmp_path)
    selected, (study, _) = _study(config, paths, trials=2)
    assert selected.optuna_settings.objective == "normal_percentile"
    assert study.direction == optuna.study.StudyDirection.MINIMIZE
    assert study.best_trial.number == 0


def test_req_007_s01_synthetic(tmp_path: Path) -> None:
    config, paths = _project(tmp_path)
    selected, split, study, outcomes = _synthetic_study(config, paths, [(0.2, 0.8)])
    best = persist_best_trial(
        config=config,
        group=selected,
        paths=paths,
        split=split,
        study=study,
        outcomes=outcomes,
    )
    saved = json.loads((paths.study_dir("XX", 0) / "best_trial.json").read_text())
    assert best.objective_name == saved["objective_name"] == "synthetic_auroc"
    assert saved["synthetic_auroc"] == 1.0
    assert saved["normal_p99"] == 0.2
    assert saved["synthetic_scores_summary"]["count"] == 1
    assert saved["threshold"] == 0.199


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
    summary = training_cli.format_training_summary(best)
    assert "暫定探索指標=" in summary
    assert "threshold=" in summary
    assert "精度" not in summary and "再現率" not in summary


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


def test_group_artifact_paths_are_distinct(tmp_path: Path) -> None:
    config, paths = _project(tmp_path, two=True)
    assert paths.checkpoint("XX", 0) != paths.checkpoint("XX", 1)
    assert paths.study_dir("XX", 0) != paths.study_dir("XX", 1)
    assert config.part.groups[1].id == 1


def test_group_req_007_s03(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config, paths = _project(tmp_path)
    selected, (study, outcomes) = _study(config, paths)
    split = split_by_source(
        load_preparation_manifest(
            paths.prepared_train("XX", 0), model="XX", group=0, allowed_split_ids={0}
        ),
        paths.prepared_train("XX", 0),
    )
    old_checkpoint = paths.checkpoint("XX", 0)
    old_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    old_checkpoint.write_bytes(b"old checkpoint")
    old_best = paths.study_dir("XX", 0) / "best_trial.json"
    old_best.write_bytes(b"old best")
    original = {
        "checkpoint": old_checkpoint.read_bytes(),
        "best": old_best.read_bytes(),
        "config": paths.model_config("XX").read_bytes(),
    }
    from app.model_training import artifacts

    replace = artifacts._replace_staged_artifact
    calls = 0

    def fail_second(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected write failure")
        replace(source, target)

    monkeypatch.setattr(artifacts, "_replace_staged_artifact", fail_second)
    with pytest.raises(OSError, match="injected write failure"):
        persist_best_trial(
            config=config,
            group=selected,
            paths=paths,
            split=split,
            study=study,
            outcomes=outcomes,
        )
    assert old_checkpoint.read_bytes() == original["checkpoint"]
    assert old_best.read_bytes() == original["best"]
    assert paths.model_config("XX").read_bytes() == original["config"]


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

    valid = load_config(tmp_path, "XX")
    validate_best_trial_contract(valid, valid.part.groups[0], paths, best)
    bad = best.model_copy(update={"checkpoint": "wrong.ckpt"})
    with pytest.raises(ValueError, match="checkpoint mismatch"):
        validate_best_trial_contract(valid, valid.part.groups[0], paths, bad)


def test_group_req_007_s05(tmp_path: Path) -> None:
    config, paths = _project(tmp_path, two=True)
    saved = {}
    for group_id, scores in ((0, [0.1, 0.2]), (1, [0.6, 0.9])):
        selected, (study, outcomes) = _study(config, paths, group=group_id)
        outcome = outcomes[study.best_trial.number]
        outcomes[study.best_trial.number] = TrialOutcome(
            outcome.validation_scores, scores, outcome.checkpoint
        )
        split = split_by_source(
            load_preparation_manifest(
                paths.prepared_train("XX", group_id),
                model="XX",
                group=group_id,
                allowed_split_ids=set(selected.range_ids),
            ),
            paths.prepared_train("XX", group_id),
        )
        saved[group_id] = persist_best_trial(
            config=config,
            group=selected,
            paths=paths,
            split=split,
            study=study,
            outcomes=outcomes,
        )
    updated = load_config(tmp_path, "XX")
    assert saved[0].threshold != saved[1].threshold
    for group_id in (0, 1):
        threshold = saved[group_id].threshold
        assert (
            updated.part.groups[group_id].optuna_settings.threshold.value == threshold
        )
        assert (
            torch.load(paths.checkpoint("XX", group_id), weights_only=False)[
                "visual_inspection"
            ]["threshold"]
            == threshold
        )
        assert (
            json.loads(
                (paths.study_dir("XX", group_id) / "best_trial.json").read_text()
            )["threshold"]
            == threshold
        )
        result = json.loads(
            (paths.study_dir("XX", group_id) / "best_trial.json").read_text()
        )
        assert result["objective_name"] == "normal_percentile"
        assert result["normal_p99"] == pytest.approx(0.2)


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


def test_group_restart_uses_tv_backbone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.common import model_adapter

    observed = {}

    class FakeModel:
        @staticmethod
        def configure_pre_processor(size):
            observed["size"] = size
            return object()

        def __init__(self, **kwargs):
            observed.update(kwargs)

    monkeypatch.setattr(model_adapter, "TunableSupersimplenet", FakeModel)
    model_adapter.create_supersimplenet(
        layers=["layer2"], image_size=256, learning_rate_multiplier=1.0
    )
    assert observed["backbone"] == "wide_resnet50_2.tv_in1k"
    assert observed["post_processor"] is False
    assert observed["size"] == (256, 256)

    config, paths = _project(tmp_path)
    from app.model_evaluation import predictor as predictor_module
    from app.model_evaluation.predictor import (
        CheckpointPredictor,
        load_checkpoint_metadata,
    )

    payload = json.loads(paths.model_config("XX").read_text())
    payload["group_detail"]["0"]["optuna_settings"]["execution"]["trials"] = 1
    paths.model_config("XX").write_text(json.dumps(payload))
    checkpoint = paths.checkpoint("XX", 0)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_text("previous")

    class FakeRunner:
        def __init__(self, directory, _device, _group):
            self.directory = directory

        def __call__(self, _parameters, _split, trial):
            self.directory.mkdir(parents=True, exist_ok=True)
            trial_checkpoint = self.directory / f"trial_{trial.number}.ckpt"
            torch.save({"state_dict": {}}, trial_checkpoint)
            return TrialOutcome([0.2], [0.1, 0.2], trial_checkpoint)

    monkeypatch.setattr(training_cli, "AnomalibTrialRunner", FakeRunner)
    _run_cli(monkeypatch, paths, group=0, restart=True)
    assert not checkpoint.read_bytes().startswith(b"previous")
    best = json.loads((paths.study_dir("XX", 0) / "best_trial.json").read_text())
    assert best["group"] == 0
    assert best["threshold"] == pytest.approx(0.199)
    assert load_checkpoint_metadata(checkpoint)["threshold"] == pytest.approx(0.199)
    reloaded = load_config(tmp_path, "XX")
    assert reloaded.part.groups[0].optuna_settings.threshold.value == pytest.approx(
        0.199
    )

    class InferenceModel:
        def __call__(self, tensor):
            return SimpleNamespace(
                pred_score=torch.tensor([0.3]),
                anomaly_map=torch.zeros((1, tensor.shape[-2], tensor.shape[-1])),
            )

    class LoadedModel:
        pre_processor = SimpleNamespace(transform=lambda tensor: tensor)
        model = InferenceModel()

        def load_state_dict(self, state):
            assert state == {}

        def to(self, _device):
            return self

        def eval(self):
            return self

    monkeypatch.setattr(
        predictor_module, "create_supersimplenet", lambda **_kw: LoadedModel()
    )
    prediction = CheckpointPredictor(
        checkpoint,
        layers=best["parameters"]["feature_layers"],
        image_size=best["parameters"]["image_size"],
        learning_rate_multiplier=best["parameters"]["learning_rate_multiplier"],
        device="cpu",
    )(np.zeros((8, 8, 3), dtype=np.uint8))
    assert prediction.score == pytest.approx(0.3)
    assert prediction.anomaly_map.shape == (8, 8)


def test_group_restart_replaces_only_selected_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from group_evaluation_helpers import FakePredictor
    from group_evaluation_helpers import project as evaluation_project

    from app.common.result_index import read_current
    from app.model_evaluation import cli as evaluation_cli
    from app.model_evaluation.predictor import load_checkpoint_metadata

    config, paths = evaluation_project(tmp_path, two=True)
    payload = json.loads(paths.model_config("XX").read_text())
    payload["groups"][1]["heatmap_range"] = {"min": 0.1, "max": 0.9}
    payload["group_detail"]["1"]["optuna_settings"]["execution"]["trials"] = 1
    paths.model_config("XX").write_text(json.dumps(payload))
    config = load_config(tmp_path, "XX")
    prepare_training(config, paths, aligner=_aligned)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "app.common.cli.select_device",
        lambda: DeviceSelection("cpu", "CPU", "test"),
    )
    monkeypatch.setattr(
        evaluation_cli,
        "CheckpointPredictor",
        lambda *_args, **_kwargs: FakePredictor(score=0.3),
    )
    evaluation_cli._test_command(model="XX", group=None)
    before_results = read_current(paths, "XX", allowed_group_ids={0, 1})
    group_zero_result = paths.results("XX") / before_results[0] / "sample.png.json"
    previous_group_zero_result = group_zero_result.read_bytes()
    old_group_one_result = json.loads(
        (paths.results("XX") / before_results[1] / "sample.png.json").read_text()
    )
    assert old_group_one_result["threshold"] == pytest.approx(0.4)
    assert old_group_one_result["overall_status"] == "normal"

    group_zero_checkpoint = paths.checkpoint("XX", 0).read_bytes()
    for group_id in (0, 1):
        history = paths.study_dir("XX", group_id) / "history.txt"
        history.parent.mkdir(parents=True, exist_ok=True)
        history.write_text(f"history {group_id}")

    class FakeRunner:
        def __init__(self, directory, _device, _group):
            self.directory = directory

        def __call__(self, _parameters, _split, trial):
            self.directory.mkdir(parents=True, exist_ok=True)
            trial_checkpoint = self.directory / f"trial_{trial.number}.ckpt"
            torch.save({"state_dict": {}}, trial_checkpoint)
            return TrialOutcome([0.2], [0.1, 0.2], trial_checkpoint)

    monkeypatch.setattr(training_cli, "AnomalibTrialRunner", FakeRunner)
    _run_cli(monkeypatch, paths, group=1, restart=True)
    assert paths.checkpoint("XX", 0).read_bytes() == group_zero_checkpoint
    assert (paths.study_dir("XX", 0) / "history.txt").read_text() == "history 0"
    assert not (paths.study_dir("XX", 1) / "history.txt").exists()
    assert (paths.study_dir("XX", 1) / "study.db").is_file()
    assert load_checkpoint_metadata(paths.checkpoint("XX", 1))[
        "threshold"
    ] == pytest.approx(0.199)

    reloaded = load_config(tmp_path, "XX")
    selected = reloaded.part.select_groups(1)[0]
    assert selected.optuna_settings.threshold.value == pytest.approx(0.199)
    assert selected.heatmap_range is not None
    assert selected.heatmap_range.model_dump() == {"min": 0.1, "max": 0.9}
    assert reloaded.part.select_groups(0)[0].optuna_settings.threshold.value == 0.4

    evaluation_cli._test_command(model="XX", group=1)
    after_results = read_current(paths, "XX", allowed_group_ids={0, 1})
    assert after_results[0] == before_results[0]
    assert after_results[1] != before_results[1]
    assert group_zero_result.read_bytes() == previous_group_zero_result
    new_group_one_result = json.loads(
        (paths.results("XX") / after_results[1] / "sample.png.json").read_text()
    )
    assert new_group_one_result["threshold"] == pytest.approx(0.199)
    assert new_group_one_result["heatmap_range"] == {"min": 0.1, "max": 0.9}
    assert new_group_one_result["overall_status"] == "anomaly"


def test_nreq_004_s01(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, paths = _project(tmp_path)
    show_conditions = training_cli.show_trial_conditions
    _stub_search(monkeypatch, paths)
    _run_cli(monkeypatch, paths, group=0)
    output = capsys.readouterr().err
    assert "バックボーン=wide_resnet50_2.tv_in1k" in output
    assert "目的=normal_percentile" in output
    show_conditions("試行 1/3 開始条件", TrialParameters(1.0, 4, 2, ["layer2"], 256))
    rendered = capsys.readouterr().err
    for value in (
        "試行 1/3",
        "学習率倍率",
        "バッチサイズ",
        "エポック数",
        "特徴層",
        "前処理画像サイズ",
    ):
        assert value in rendered


def test_nreq_004_s02(capsys: pytest.CaptureFixture[str]) -> None:
    for state, value, label in (
        (optuna.trial.TrialState.COMPLETE, 0.2, "完了"),
        (optuna.trial.TrialState.PRUNED, None, "枝刈り"),
        (optuna.trial.TrialState.FAIL, None, "失敗"),
    ):
        trial = optuna.create_trial(state=state, value=value, params={})
        training_cli.show_trial_outcome(trial)
        message = capsys.readouterr().err
        assert label in message
        assert ("暫定探索指標=0.2" in message) == (
            state == optuna.trial.TrialState.COMPLETE
        )
    failed = optuna.create_trial(
        state=optuna.trial.TrialState.FAIL,
        params={},
        user_attrs={"failure_reason": "ValueError: invalid score"},
    )
    training_cli.show_trial_outcome(failed)
    assert "理由=ValueError: invalid score" in capsys.readouterr().err


def test_nreq_004_s03(tmp_path: Path) -> None:
    config, paths = _project(tmp_path)
    selected, (study, _outcomes) = _study(config, paths, trials=1)
    assert len(study.trials) == 1
    selected.optuna_settings.execution.trials = 3
    resumed = create_study(config, selected, paths.study_dir("XX", 0) / "study.db")
    manifest = load_preparation_manifest(
        paths.prepared_train("XX", 0),
        model="XX",
        group=0,
        allowed_split_ids={0},
        fingerprint=preparation_fingerprint(config, group=selected),
    )
    split = split_by_source(manifest, paths.prepared_train("XX", 0))
    shown = []

    def runner(parameters, split, trial):
        del parameters, split
        checkpoint = paths.study_dir("XX", 0) / f"resume_{trial.number}.ckpt"
        torch.save({"state_dict": {}}, checkpoint)
        return TrialOutcome([0.2], [0.1], checkpoint)

    run_search(
        selected,
        split,
        resumed,
        runner,
        on_trial_start=lambda number, _parameters: shown.append(number),
    )
    assert shown == [1, 2]
