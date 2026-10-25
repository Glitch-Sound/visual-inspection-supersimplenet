from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest
import torch
import typer
from conftest import write_test_image
from group_evaluation_helpers import FakePredictor, aligned, project, recorder

from app.common.config import load_config
from app.common.result_index import create_result_stage, recover_results
from app.image_preparation.imaging import AlignmentError
from app.image_preparation.preparation import prepare_testing
from app.model_evaluation import cli as evaluation_cli
from app.model_evaluation import evaluation
from app.model_evaluation.cli import _test_command
from app.model_evaluation.evaluation import (
    _heatmap,
    effective_threshold,
    evaluate_split,
    require_heatmap_range,
    validate_score_contract,
)
from app.model_evaluation.predictor import Prediction, load_checkpoint_metadata


def _run(
    monkeypatch: pytest.MonkeyPatch,
    paths,
    *,
    group=None,
    score=0.5,
    predictor_factory=None,
):
    run = recorder()
    monkeypatch.setattr(
        evaluation_cli, "_run", lambda _cmd, _model, action, **_kw: action(paths, run)
    )
    monkeypatch.setattr(
        evaluation_cli,
        "CheckpointPredictor",
        predictor_factory or (lambda *_a, **_kw: FakePredictor(score=score)),
    )
    return _test_command(model="XX", group=group), run


def _current(paths) -> dict[int, str]:
    return {
        group: paths.group_name(group)
        for group in (0, 1)
        if paths.result_group("XX", group).is_dir()
    }


def _two_sources(root: Path):
    config, paths = project(root, two=True)
    write_test_image(paths.original_test("XX") / "second.png", size=32)
    prepare_testing(config, paths, aligner=aligned)
    return paths


def test_result_all_groups(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths)
    assert set(_current(paths)) == {0, 1}
    for group in (0, 1):
        assert (paths.result_group("XX", group) / "sample.png.json").is_file()


def test_result_selected_group(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths, group=1)
    assert set(_current(paths)) == {1}


def test_result_unknown_group(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path)
    with pytest.raises(ValueError, match="available groups"):
        _run(monkeypatch, paths, group=9)
    assert _current(paths) == {}


def test_result_missing_model_preserves_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths)
    before = {
        group: (paths.result_group("XX", group) / "sample.png.json").read_bytes()
        for group in (0, 1)
    }
    paths.checkpoint("XX", 1).unlink()
    with pytest.raises(ValueError, match="group 1 failed.*group_01.ckpt"):
        _run(monkeypatch, paths)
    assert {
        group: (paths.result_group("XX", group) / "sample.png.json").read_bytes()
        for group in (0, 1)
    } == before


@pytest.mark.parametrize("missing", ["checkpoint", "best_trial"])
def test_req_023_s03_cli_input_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    missing: str,
) -> None:
    _, paths = project(tmp_path, two=True)
    missing_path = (
        paths.checkpoint("XX", 1)
        if missing == "checkpoint"
        else paths.study_dir("XX", 1) / "best_trial.json"
    )
    missing_path.unlink()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("app.common.cli.select_device", lambda: recorder().device)

    with pytest.raises(typer.Exit) as error:
        _test_command(model="XX", group=1)

    assert error.value.exit_code == 2
    record = json.loads(capsys.readouterr().out)
    assert record["exit_code"] == 2
    assert "group 1 failed" in record["errors"][0]
    assert str(missing_path) in record["errors"][0]


@pytest.mark.parametrize("failure", ["evaluation", "result_image_write"])
def test_result_later_group_failure_keeps_all_old(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths)
    before = {
        group: (paths.result_group("XX", group) / "sample.png.json").read_bytes()
        for group in (0, 1)
    }
    if failure == "evaluation":
        original = evaluation_cli.evaluate_model

        def fail_second(config, group, *args, **kwargs):
            if group.id == 1:
                raise RuntimeError("injected failure")
            return original(config, group, *args, **kwargs)

        monkeypatch.setattr(evaluation_cli, "evaluate_model", fail_second)
    else:
        original_write = evaluation.write_image

        def fail_image_write(path, image):
            if path.parent.name == "group_01":
                raise OSError("injected image write failure")
            return original_write(path, image)

        monkeypatch.setattr(evaluation, "write_image", fail_image_write)
    with pytest.raises(RuntimeError, match="group 1 failed"):
        _run(monkeypatch, paths)
    assert {
        group: (paths.result_group("XX", group) / "sample.png.json").read_bytes()
        for group in (0, 1)
    } == before


def test_group_req_010_s01(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths, score=0.2)
    current = _current(paths)
    first = paths.results("XX") / current[0] / "sample.png.json"
    second = paths.results("XX") / current[1] / "sample.png.json"
    for result in (first, second):
        splits = json.loads(result.read_text())["splits"]
        assert {item["split_id"] for item in splits} == (
            {0, 1} if result == first else {0}
        )
        for split in splits:
            assert split["score"] == pytest.approx(0.2)
            assert split["status"] == "normal"
            original = cv2.imread(str(paths.prepared_test("XX") / split["image"]))
            rendered = cv2.imread(str(result.parent / split["result_image"]))
            assert original is not None and rendered is not None
            assert np.array_equal(rendered, original)


def test_group_req_010_s02(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths, group=1, score=0.8)
    result = paths.results("XX") / _current(paths)[1] / "sample.png.json"
    split = json.loads(result.read_text())["splits"][0]
    original = cv2.imread(str(paths.prepared_test("XX") / split["image"]))
    rendered = cv2.imread(str(result.parent / split["result_image"]))
    assert original is not None and rendered is not None
    assert split["score"] == pytest.approx(0.8)
    assert split["status"] == "anomaly"
    assert rendered.shape == (original.shape[0], original.shape[1] * 2, 3)
    assert np.array_equal(rendered[:, : original.shape[1]], original)
    assert not np.array_equal(rendered[:, original.shape[1] :], original)


def test_group_req_010_s03(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from app.model_evaluation import predictor as predictor_module

    image = np.full((8, 8, 3), 127, dtype=np.uint8)
    seen = []
    preprocessing = []

    def model_preprocess(tensor):
        preprocessing.append(tensor.clone())
        return tensor + 0.25

    class InferenceModel:
        def __call__(self, tensor):
            seen.append(tensor.clone())
            return SimpleNamespace(
                pred_score=torch.tensor([0.3]), anomaly_map=torch.zeros((1, 8, 8))
            )

    class Model:
        pre_processor = SimpleNamespace(transform=model_preprocess)
        model = InferenceModel()

        def load_state_dict(self, _state):
            pass

        def to(self, _device):
            pass

        def eval(self):
            pass

    monkeypatch.setattr(
        predictor_module, "create_supersimplenet", lambda **_kw: Model()
    )
    checkpoint = tmp_path / "model.ckpt"
    torch.save({"state_dict": {}}, checkpoint)
    predictor = predictor_module.CheckpointPredictor(
        checkpoint,
        layers=["layer2"],
        image_size=256,
        learning_rate_multiplier=1.0,
        device="cpu",
    )
    prediction = predictor(image)
    assert prediction.score == pytest.approx(0.3)
    assert len(preprocessing) == len(seen) == 1
    assert torch.allclose(preprocessing[0], torch.full((1, 3, 8, 8), 127 / 255))
    assert torch.allclose(seen[0], torch.full((1, 3, 8, 8), 127 / 255 + 0.25))


def test_group_req_010_s04(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config, _ = project(tmp_path)
    heatmap_range = require_heatmap_range(config.part.groups[0].ranges[0])
    image = np.zeros((2, 2, 3), dtype=np.uint8)
    low, high = heatmap_range.min, heatmap_range.max
    common = (low + high) / 2
    first_map = np.array([[low - 1, common], [high + 1, common]], dtype=np.float32)
    second_map = np.array([[common, high + 1], [common, low - 1]], dtype=np.float32)
    first = _heatmap(image, first_map, heatmap_range)
    second = _heatmap(image, second_map, heatmap_range)
    assert np.array_equal(first[0, 1], second[0, 0])
    assert np.array_equal(first[1, 0], second[0, 1])
    assert np.array_equal(first[0, 0], second[1, 1])
    assert not np.array_equal(first[0, 0], first[1, 0])


def test_result_replace_after_all_groups_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths, score=0.2)
    old = (paths.result_group("XX", 0) / "sample.png.json").read_bytes()
    _run(monkeypatch, paths, score=0.8)
    assert (paths.result_group("XX", 0) / "sample.png.json").read_bytes() != old
    assert set(_current(paths)) == {0, 1}
    assert not list(paths.results("XX").glob(".backup-*"))


def test_result_single_group_preserves_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths, score=0.2)
    other = paths.result_group("XX", 1) / "sample.png.json"
    before = (other.read_bytes(), other.stat().st_mtime_ns)
    _run(monkeypatch, paths, group=0, score=0.8)
    assert (other.read_bytes(), other.stat().st_mtime_ns) == before
    assert (
        json.loads((paths.result_group("XX", 0) / "sample.png.json").read_text())[
            "overall_status"
        ]
        == "anomaly"
    )


def test_result_stage_failure_preserves_all_groups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths)
    before = {
        group: (paths.result_group("XX", group) / "sample.png.json").read_bytes()
        for group in (0, 1)
    }
    original = evaluation_cli.evaluate_model

    def fail_later(config, selected, *args, **kwargs):
        if selected.id == 1:
            raise OSError("interrupted")
        return original(config, selected, *args, **kwargs)

    monkeypatch.setattr(evaluation_cli, "evaluate_model", fail_later)
    with pytest.raises(RuntimeError, match="group 1 failed: interrupted"):
        _run(monkeypatch, paths)
    assert {
        group: (paths.result_group("XX", group) / "sample.png.json").read_bytes()
        for group in (0, 1)
    } == before
    assert not list(paths.results("XX").glob(".stage-*"))


def test_result_recovery_after_publish_interrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = project(tmp_path)
    _run(monkeypatch, paths)
    root = paths.results("XX")
    target = paths.result_group("XX", 0)
    old = (target / "sample.png.json").read_bytes()
    backup = root / f".backup-group_00-{'a' * 32}"
    target.replace(backup)
    original = evaluation_cli.evaluate_model

    def assert_restored(*args, **kwargs):
        assert (target / "sample.png.json").read_bytes() == old
        return original(*args, **kwargs)

    monkeypatch.setattr(evaluation_cli, "evaluate_model", assert_restored)
    _run(monkeypatch, paths)
    assert not backup.exists()
    target.replace(backup)
    target.mkdir()
    (target / "sample.png.json").write_text("new")
    recover_results(paths, "XX")
    assert (target / "sample.png.json").read_text() == "new"
    assert not backup.exists()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "marker.txt").write_text("safe")
    bad_backup = root / f".backup-group_00-{'b' * 32}"
    bad_backup.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="invalid result group directory"):
        _run(monkeypatch, paths)
    assert (outside / "marker.txt").read_text() == "safe"


@pytest.mark.parametrize("component", ["parent", "group"])
def test_result_rejects_symlink_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, component: str
) -> None:
    _, paths = project(tmp_path)
    root = paths.results("XX")
    root.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "marker.txt"
    marker.write_text("safe")
    if component == "parent":
        root.rmdir()
        root.symlink_to(outside, target_is_directory=True)
    else:
        paths.result_group("XX", 0).symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        _run(monkeypatch, paths)
    assert marker.read_text() == "safe"


def test_result_full_rerun_replaces_mixed_groups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths, score=0.2)
    _run(monkeypatch, paths, group=0, score=0.8)
    _run(monkeypatch, paths, score=0.8)
    for group in (0, 1):
        result = json.loads(
            (paths.result_group("XX", group) / "sample.png.json").read_text()
        )
        assert result["overall_status"] == "anomaly"


def test_result_residue_does_not_block_preparation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = project(tmp_path)
    stale = paths.results("XX") / f".stage-{'a' * 32}"
    stale.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    from app.common.cli import _run as execute

    execute("check", "XX", lambda _paths, _recorder: "ok")
    assert stale.exists()


def test_result_full_run_removes_unconfigured_groups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = project(tmp_path)
    root = paths.results("XX")
    stale = root / "group_09"
    stale.mkdir(parents=True)
    (stale / "old.png.json").write_text("old")
    current = root / "current.json"
    current.write_text("legacy")
    generations = root / "generations"
    generations.mkdir()
    (generations / "marker").write_text("legacy")
    _run(monkeypatch, paths)
    assert not stale.exists()
    assert current.read_text() == "legacy"
    assert (generations / "marker").read_text() == "legacy"


def test_result_cleanup_managed_entries_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = project(tmp_path)
    _run(monkeypatch, paths)
    root = paths.results("XX")
    old = paths.result_group("XX", 0)
    backup = root / f".backup-group_00-{'b' * 32}"
    old.replace(backup)
    stale = root / f".stage-{'a' * 32}"
    stale.mkdir()
    unmanaged = root / "notes.txt"
    unmanaged.write_text("safe")
    _run(monkeypatch, paths)
    assert not stale.exists()
    assert not backup.exists()
    assert (old / "sample.png.json").is_file()
    assert unmanaged.read_text() == "safe"


def test_result_stale_stage_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = project(tmp_path)
    _run(monkeypatch, paths)
    stale = create_result_stage(paths, "XX")
    (stale / "group_00").mkdir()
    (stale / "group_00" / "sample.png.json.tmp").write_text("partial")
    _run(monkeypatch, paths)
    assert not stale.exists()
    assert (paths.result_group("XX", 0) / "sample.png.json").is_file()


def test_result_full_run_failure_preserves_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _two_sources(tmp_path)
    _run(monkeypatch, paths)
    old = {
        group: (paths.result_group("XX", group) / "sample.png.json").read_bytes()
        for group in (0, 1)
    }
    original_write = evaluation.write_inspection_result

    def fail_late(result, output):
        if result.group == 1 and result.source_image == "second.png":
            raise OSError("late result write failed")
        original_write(result, output)

    monkeypatch.setattr(evaluation, "write_inspection_result", fail_late)
    with pytest.raises(RuntimeError, match="group 1 failed: late result write failed"):
        _run(monkeypatch, paths)
    assert {
        group: (paths.result_group("XX", group) / "sample.png.json").read_bytes()
        for group in (0, 1)
    } == old


def test_result_rerun_drops_old_source_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = project(tmp_path)
    _run(monkeypatch, paths)
    group = paths.result_group("XX", 0)
    (group / "removed.png.json").write_text("old")
    (group / "removed_00.png_result.png").write_bytes(b"old")
    _run(monkeypatch, paths)
    assert sorted(path.name for path in group.iterdir()) == [
        "sample.png.json",
        "sample_00.png_result.png",
        "sample_01.png_result.png",
    ]


def test_group_req_016_s01(tmp_path: Path) -> None:
    config, paths = project(tmp_path)
    group = config.part.groups[0]
    metadata = load_checkpoint_metadata(paths.checkpoint("XX", 0))
    assert validate_score_contract(config, group, metadata) == 0.4


def test_group_req_016_s02(tmp_path: Path) -> None:
    _, paths = project(tmp_path)
    torch.save({"state_dict": {}}, paths.checkpoint("XX", 0))
    with pytest.raises(ValueError, match="metadata"):
        load_checkpoint_metadata(paths.checkpoint("XX", 0))


def test_group_req_016_s03(tmp_path: Path) -> None:
    config, paths = project(tmp_path)
    metadata = load_checkpoint_metadata(paths.checkpoint("XX", 0))
    metadata["group"] = 1
    with pytest.raises(ValueError, match="group mismatch"):
        validate_score_contract(config, config.part.groups[0], metadata)


def test_group_req_018_s01(tmp_path: Path) -> None:
    config, _ = project(tmp_path)
    group = config.part.groups[0]
    assert effective_threshold(group.ranges[0], 0.4) == 0.4


def test_group_req_018_s02(tmp_path: Path) -> None:
    config, _ = project(tmp_path)
    assert config.part.groups[0].ranges[0].inspection_threshold is None
    assert effective_threshold(config.part.groups[0].ranges[0], 0.4) == 0.4


def test_group_req_018_s03(tmp_path: Path) -> None:
    config, _ = project(tmp_path)
    group = config.part.groups[0]
    group.ranges[0].inspection_threshold = 0.7
    assert effective_threshold(group.ranges[0], 0.4) == 0.7
    assert group.optuna_settings.threshold.value == 0.4


@pytest.mark.parametrize("value", [0.0, 1.0])
def test_group_req_018_s04(tmp_path: Path, value: float) -> None:
    config, _ = project(tmp_path)
    group = config.part.groups[0]
    group.ranges[0].inspection_threshold = value
    assert effective_threshold(group.ranges[0], 0.4) == value
    image = np.zeros((4, 4, 3), dtype=np.uint8)
    split = evaluate_split(
        image_path=Path("input.png"),
        image=image,
        prediction=Prediction(value, np.zeros((4, 4), dtype=np.float32)),
        split_id=0,
        threshold=value,
        threshold_source="configured",
        heatmap_range=require_heatmap_range(group.ranges[0]),
        result_path=tmp_path / "result.png",
    )
    assert split.status == "anomaly"
    assert split.score == value


@pytest.mark.parametrize("value", [-0.1, 1.1, "bad", True])
def test_group_req_018_s05(tmp_path: Path, value: object) -> None:
    _, paths = project(tmp_path)
    payload = json.loads(paths.model_config("XX").read_text())
    payload["groups"][0]["ranges"][0]["inspection_threshold"] = value
    paths.model_config("XX").write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="inspection_threshold"):
        load_config(tmp_path, "XX")


def test_group_req_018_s06(tmp_path: Path) -> None:
    config, paths = project(tmp_path)
    group = config.part.groups[0]
    group.optuna_settings.threshold.value = 0.6
    metadata = load_checkpoint_metadata(paths.checkpoint("XX", 0))
    with pytest.raises(ValueError, match="threshold"):
        validate_score_contract(config, group, metadata)


def test_group_req_019_s01(tmp_path: Path) -> None:
    config, _ = project(tmp_path)
    group = config.part.groups[0]
    image = np.zeros((2, 2, 3), dtype=np.uint8)
    scale = require_heatmap_range(group.ranges[0])
    middle = (scale.min + scale.max) / 2
    first = np.array(
        [[scale.min - 1, middle], [scale.max + 1, middle]], dtype=np.float32
    )
    second = np.array(
        [[middle, scale.max + 2], [middle, scale.min - 2]], dtype=np.float32
    )
    rendered_first = _heatmap(image, first, scale)
    rendered_second = _heatmap(image, second, scale)
    assert np.array_equal(rendered_first[0, 1], rendered_second[0, 0])
    assert np.array_equal(rendered_first[1, 0], rendered_second[0, 1])
    assert np.array_equal(rendered_first[0, 0], rendered_second[1, 1])
    changed_scale = scale.model_copy(update={"max": scale.max + 1})
    first_result = evaluate_split(
        image_path=Path("input.png"),
        image=image,
        prediction=Prediction(0.8, first),
        split_id=0,
        threshold=0.4,
        threshold_source="provisional",
        heatmap_range=scale,
        result_path=tmp_path / "first.png",
    )
    second_result = evaluate_split(
        image_path=Path("input.png"),
        image=image,
        prediction=Prediction(0.8, first),
        split_id=0,
        threshold=0.4,
        threshold_source="provisional",
        heatmap_range=changed_scale,
        result_path=tmp_path / "second.png",
    )
    assert (first_result.score, first_result.status) == (
        second_result.score,
        second_result.status,
    )
    first_image = cv2.imread(str(tmp_path / "first.png"))
    second_image = cv2.imread(str(tmp_path / "second.png"))
    assert first_image is not None and second_image is not None
    assert not np.array_equal(first_image, second_image)


def test_result_non_tty_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _two_sources(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("app.common.cli.select_device", lambda: recorder().device)
    monkeypatch.setattr(
        evaluation_cli,
        "CheckpointPredictor",
        lambda *_args, **_kwargs: FakePredictor(score=0.5),
    )
    capsys.readouterr()
    _test_command(model="XX", group=None)
    captured = capsys.readouterr()
    stderr = captured.err
    assert stderr.count("検査進捗 0/2") == 1
    assert stderr.count("検査進捗 1/2") == 1
    assert stderr.count("検査進捗 2/2") == 1
    assert len(captured.out.splitlines()) == 1
    assert json.loads(captured.out)["exit_code"] == 0


def test_result_tty_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _two_sources(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("app.common.cli.select_device", lambda: recorder().device)
    monkeypatch.setattr(
        evaluation_cli,
        "CheckpointPredictor",
        lambda *_args, **_kwargs: FakePredictor(score=0.5),
    )
    updates = []

    class FakeProgress:
        def __init__(self, *_args, **_kwargs):
            pass

        def start(self):
            pass

        def stop(self):
            pass

        def add_task(self, _description, *, total):
            assert total == 2
            return 1

        def update(self, _task_id, *, completed, total):
            updates.append((completed, total))

    monkeypatch.setattr(evaluation_cli.sys.stderr, "isatty", lambda: True)
    monkeypatch.setattr(evaluation_cli, "Progress", FakeProgress)
    capsys.readouterr()
    _test_command(model="XX", group=None)
    assert updates == [(0, 2), (1, 2), (2, 2)]
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1
    assert json.loads(captured.out)["exit_code"] == 0


def test_command_progress_single_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = _two_sources(tmp_path)
    capsys.readouterr()
    _run(monkeypatch, paths, group=1)
    stderr = capsys.readouterr().err
    assert [line for line in stderr.splitlines() if "検査進捗" in line] == [
        "検査進捗 0/2",
        "検査進捗 1/2",
        "検査進捗 2/2",
    ]
    assert set(_current(paths)) == {1}


def test_command_progress_during_inference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = _two_sources(tmp_path)
    calls = []

    class TrackingPredictor(FakePredictor):
        def __call__(self, image):
            calls.append(capsys.readouterr().err)
            return super().__call__(image)

    _run(
        monkeypatch,
        paths,
        group=1,
        predictor_factory=lambda *_a, **_kw: TrackingPredictor(score=0.5),
    )
    assert len(calls) == 2
    assert "検査進捗 1/2" not in calls[0]
    assert "検査進捗 1/2" in calls[1]


def test_result_progress_counts_undetermined(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = _two_sources(tmp_path)

    class FailingPredictor:
        def __call__(self, _image):
            raise RuntimeError("inference failed")

    capsys.readouterr()
    _run(monkeypatch, paths, predictor_factory=lambda *_a, **_kw: FailingPredictor())
    stderr = capsys.readouterr().err
    assert stderr.count("検査進捗 1/2") == 1
    assert stderr.count("検査進捗 2/2") == 1
    for group, result_dir in _current(paths).items():
        for source in ("sample.png", "second.png"):
            result = json.loads(
                (paths.results("XX") / result_dir / f"{source}.json").read_text()
            )
            assert result["group"] == group
            assert result["overall_status"] == "undetermined"


def test_command_progress_cli_undetermined_exit_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _two_sources(tmp_path)
    config = load_config(tmp_path, "XX")
    alignments = 0

    def align_or_fail(image, reference, settings):
        nonlocal alignments
        alignments += 1
        if alignments == 2:
            raise AlignmentError("too few matches")
        return aligned(image, reference, settings)

    prepare_testing(config, paths, aligner=align_or_fail)

    class FailingPredictor:
        def __call__(self, _image):
            raise RuntimeError("inference failed")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("app.common.cli.select_device", lambda: recorder().device)
    monkeypatch.setattr(
        evaluation_cli,
        "CheckpointPredictor",
        lambda *_args, **_kwargs: FailingPredictor(),
    )
    capsys.readouterr()
    _test_command(model="XX", group=None)
    captured = capsys.readouterr()
    for count in (0, 1, 2):
        assert captured.err.count(f"検査進捗 {count}/2") == 1
    assert "警告:" in captured.err
    assert "too few matches" in captured.err
    assert "エラー:" in captured.err
    assert "inference failed" in captured.err
    assert "終了: test 処理完了・一部エラー=" in captured.err
    assert len(captured.out.splitlines()) == 1
    record = json.loads(captured.out)
    assert record["exit_code"] == 0
    assert record["warnings"] and record["errors"]
    for group, result_dir in _current(paths).items():
        for source_name, recapture_required in (
            ("sample.png", False),
            ("second.png", True),
        ):
            result = json.loads(
                (paths.results("XX") / result_dir / f"{source_name}.json").read_text()
            )
            assert result["group"] == group
            assert result["overall_status"] == "undetermined"
            assert result["alignment"]["recapture_required"] is recapture_required


@pytest.mark.parametrize("failure", ["later_group", "final_write"])
def test_command_progress_cli_failure_exit_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: str,
) -> None:
    paths = _two_sources(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("app.common.cli.select_device", lambda: recorder().device)
    monkeypatch.setattr(
        evaluation_cli,
        "CheckpointPredictor",
        lambda *_args, **_kwargs: FakePredictor(score=0.5),
    )
    _test_command(model="XX", group=None)
    before = {
        group: (paths.result_group("XX", group) / "sample.png.json").read_bytes()
        for group in (0, 1)
    }

    reason = ""
    if failure == "later_group":
        original_evaluate = evaluation_cli.evaluate_model

        def fail_later_group(config, group, *args, **kwargs):
            if group.id == 1:
                raise RuntimeError("injected later group failure")
            return original_evaluate(config, group, *args, **kwargs)

        monkeypatch.setattr(evaluation_cli, "evaluate_model", fail_later_group)
        reason = "group 1 failed: injected later group failure"
    elif failure == "final_write":
        original_write = evaluation.InspectionResult.write_json
        writes = 0

        def fail_final_write(result, output):
            nonlocal writes
            if output.parent.name == "group_01" and result.source_image == "second.png":
                writes += 1
                if writes == 2:
                    raise OSError("injected final write failure")
            return original_write(result, output)

        monkeypatch.setattr(evaluation.InspectionResult, "write_json", fail_final_write)
        reason = "group 1 failed: injected final write failure"

    capsys.readouterr()
    with pytest.raises(typer.Exit) as error:
        _test_command(model="XX", group=None)
    assert error.value.exit_code == 3
    captured = capsys.readouterr()
    assert captured.err.count("検査進捗 0/2") == 1
    if failure == "later_group":
        assert "検査進捗 1/2" not in captured.err
    else:
        assert captured.err.count("検査進捗 1/2") == 1
    assert "検査進捗 2/2" not in captured.err
    assert f"処理失敗: {reason}" in captured.err
    assert "終了: test 未完了" in captured.err
    assert len(captured.out.splitlines()) == 1
    record = json.loads(captured.out)
    assert record["exit_code"] == 3
    assert reason in record["errors"]
    assert {
        group: (paths.result_group("XX", group) / "sample.png.json").read_bytes()
        for group in (0, 1)
    } == before


def test_command_progress_stops_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = _two_sources(tmp_path)
    _run(monkeypatch, paths)
    before = (paths.result_group("XX", 0) / "sample.png.json").read_bytes()
    original = evaluation_cli.evaluate_model

    def fail_second(config, group, *args, **kwargs):
        if group.id == 1:
            raise RuntimeError("injected failure")
        return original(config, group, *args, **kwargs)

    monkeypatch.setattr(evaluation_cli, "evaluate_model", fail_second)
    capsys.readouterr()
    with pytest.raises(RuntimeError, match="group 1 failed"):
        _run(monkeypatch, paths)
    stderr = capsys.readouterr().err
    assert stderr.count("検査進捗 0/2") == 1
    assert "検査進捗 1/2" not in stderr
    assert (paths.result_group("XX", 0) / "sample.png.json").read_bytes() == before


def test_command_progress_stops_before_failed_result_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _two_sources(tmp_path)
    _run(monkeypatch, paths)
    before = (paths.result_group("XX", 0) / "sample.png.json").read_bytes()
    write_result = evaluation.write_inspection_result

    def fail_second_result(result, output):
        if output.parent.name == "group_01" and result.source_image == "second.png":
            raise OSError("injected result write failure")
        write_result(result, output)

    monkeypatch.setattr(evaluation, "write_inspection_result", fail_second_result)
    capsys.readouterr()
    with pytest.raises(RuntimeError, match="group 1 failed"):
        _run(monkeypatch, paths)
    stderr = capsys.readouterr().err
    assert stderr.count("検査進捗 1/2") == 1
    assert "検査進捗 2/2" not in stderr
    assert (paths.result_group("XX", 0) / "sample.png.json").read_bytes() == before


@pytest.mark.parametrize("failure", ["final_write", "publish"])
def test_result_publish_failure_does_not_finish_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: str,
) -> None:
    paths = _two_sources(tmp_path)
    _run(monkeypatch, paths)
    before = {
        group: (paths.result_group("XX", group) / "sample.png.json").read_bytes()
        for group in (0, 1)
    }
    if failure == "final_write":
        original = evaluation.InspectionResult.write_json
        writes = 0

        def fail_rewrite(result, output):
            nonlocal writes
            if output.parent.name == "group_01" and result.source_image == "second.png":
                writes += 1
                if writes == 2:
                    raise OSError("injected final write failure")
            return original(result, output)

        monkeypatch.setattr(evaluation.InspectionResult, "write_json", fail_rewrite)
    else:
        monkeypatch.setattr(
            evaluation_cli,
            "publish_group",
            lambda *_args: (_ for _ in ()).throw(OSError("injected publish failure")),
        )
    capsys.readouterr()
    with pytest.raises(RuntimeError, match="injected"):
        _run(monkeypatch, paths)
    stderr = capsys.readouterr().err
    assert "検査進捗 2/2" not in stderr
    if failure == "final_write":
        assert "検査進捗 1/2" in stderr
    assert {
        group: (paths.result_group("XX", group) / "sample.png.json").read_bytes()
        for group in (0, 1)
    } == before


def test_command_progress_preserves_single_stdout_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _two_sources(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "app.common.cli.select_device",
        lambda: recorder().device,
    )
    monkeypatch.setattr(
        evaluation_cli,
        "CheckpointPredictor",
        lambda *_args, **_kwargs: FakePredictor(score=0.2),
    )
    capsys.readouterr()
    _test_command(model="XX", group=None)
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1
    record = json.loads(captured.out)
    assert record["exit_code"] == 0
    assert record["groups"] == [0, 1]
    assert captured.err.count("検査進捗 2/2") == 1


@pytest.mark.parametrize("value", [None, {"min": 1, "max": 1}, {"min": True, "max": 2}])
def test_group_req_019_s02(tmp_path: Path, value: object) -> None:
    _, paths = project(tmp_path)
    payload = json.loads(paths.model_config("XX").read_text())
    payload["groups"][0]["ranges"][0]["heatmap_range"] = value
    paths.model_config("XX").write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="heatmap_range"):
        load_config(tmp_path, "XX")


def test_per_range_group_results_are_distinct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = project(tmp_path, two=True)
    payload = json.loads(paths.model_config("XX").read_text())
    group_zero = payload["groups"][0]["ranges"]
    group_zero[0]["inspection_threshold"] = 0.3
    group_zero[0]["heatmap_range"] = {"min": 0.2, "max": 0.6}
    group_zero[1]["heatmap_range"] = {"min": 0.0, "max": 2.0}
    payload["groups"][1]["ranges"][0]["inspection_threshold"] = 0.9
    paths.model_config("XX").write_text(json.dumps(payload))
    _run(monkeypatch, paths, score=0.5)
    first = json.loads((paths.result_group("XX", 0) / "sample.png.json").read_text())
    second = json.loads((paths.result_group("XX", 1) / "sample.png.json").read_text())
    assert "threshold" not in first and "heatmap_range" not in first
    assert [
        (s["split_id"], s["status"], s["threshold_source"]) for s in first["splits"]
    ] == [
        (0, "anomaly", "configured"),
        (1, "anomaly", "provisional"),
    ]
    assert [s["threshold"] for s in first["splits"]] == [0.3, 0.4]
    assert [s["heatmap_range"] for s in first["splits"]] == [
        {"min": 0.2, "max": 0.6},
        {"min": 0.0, "max": 2.0},
    ]
    assert first["overall_status"] == "anomaly"
    assert [
        (s["status"], s["threshold"], s["threshold_source"]) for s in second["splits"]
    ] == [("normal", 0.9, "configured")]
    assert second["overall_status"] == "normal"


def test_per_range_values_change_without_repreparation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, paths = project(tmp_path)
    prepared = paths.prepared_test("XX") / "manifest.json"
    before_manifest = prepared.read_bytes()
    before_checkpoint = paths.checkpoint("XX", 0).read_bytes()
    original_fingerprint = evaluation.preparation_fingerprint(config)
    _run(monkeypatch, paths, score=0.5)
    first = json.loads((paths.result_group("XX", 0) / "sample.png.json").read_text())
    payload = json.loads(paths.model_config("XX").read_text())
    payload["groups"][0]["ranges"][0]["inspection_threshold"] = 0.8
    payload["groups"][0]["ranges"][0]["heatmap_range"] = {"min": -1.0, "max": 2.0}
    paths.model_config("XX").write_text(json.dumps(payload))
    assert (
        evaluation.preparation_fingerprint(load_config(tmp_path, "XX"))
        == original_fingerprint
    )
    _run(monkeypatch, paths, score=0.5)
    second = json.loads((paths.result_group("XX", 0) / "sample.png.json").read_text())
    assert first["splits"][0]["status"] == "anomaly"
    assert second["splits"][0]["status"] == "normal"
    assert second["splits"][0]["threshold"] == 0.8
    assert second["splits"][0]["heatmap_range"] == {"min": -1.0, "max": 2.0}
    assert prepared.read_bytes() == before_manifest
    assert paths.checkpoint("XX", 0).read_bytes() == before_checkpoint


def test_per_range_threshold_start_display(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, paths = project(tmp_path)
    payload = json.loads(paths.model_config("XX").read_text())
    payload["groups"][0]["ranges"][0]["inspection_threshold"] = 0.7
    paths.model_config("XX").write_text(json.dumps(payload))
    capsys.readouterr()
    _run(monkeypatch, paths, score=0.5)
    output = capsys.readouterr().err
    result = json.loads((paths.result_group("XX", 0) / "sample.png.json").read_text())
    for split in result["splits"]:
        assert (
            f"グループ 0 分割 {split['split_id']} 判定閾値: "
            f"{split['threshold']} ({split['threshold_source']})"
        ) in output


def test_per_range_missing_threshold(tmp_path: Path) -> None:
    _, paths = project(tmp_path)
    payload = json.loads(paths.model_config("XX").read_text())
    payload["groups"][0]["ranges"][0].pop("inspection_threshold")
    paths.model_config("XX").write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="group 0 range 0.*inspection_threshold"):
        load_config(tmp_path, "XX")
