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
from typer.testing import CliRunner

from app.common.config import load_config
from app.common.result_index import (
    create_generation,
    read_current,
)
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
    return read_current(paths, "XX", allowed_group_ids={0, 1})


def _two_sources(root: Path):
    config, paths = project(root, two=True)
    write_test_image(paths.original_test("XX") / "second.png", size=32)
    prepare_testing(config, paths, aligner=aligned)
    return paths


def test_group_req_023_s01(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths)
    assert set(_current(paths)) == {0, 1}


def test_group_req_023_s02(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths, group=1)
    assert set(_current(paths)) == {1}


def test_group_req_023_s04(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path)
    with pytest.raises(ValueError, match="available groups"):
        _run(monkeypatch, paths, group=9)


def test_group_req_023_s03(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths)
    before = _current(paths)
    old_result = paths.results("XX") / before[1] / "sample.png.json"
    old_contents = old_result.read_bytes()
    paths.checkpoint("XX", 1).unlink()
    with pytest.raises(ValueError, match="group 1"):
        _run(
            monkeypatch,
            paths,
            predictor_factory=lambda *_a, **_kw: pytest.fail("predictor started"),
        )
    assert _current(paths) == before
    assert old_result.read_bytes() == old_contents


@pytest.mark.parametrize("failure", ["evaluation", "result_image_write"])
def test_group_req_023_s05(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths)
    before = _current(paths)
    old_result = paths.results("XX") / before[1] / "sample.png.json"
    old_contents = old_result.read_bytes()
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
            if path.parent.name == "group_1":
                raise OSError("injected image write failure")
            return original_write(path, image)

        monkeypatch.setattr(evaluation, "write_image", fail_image_write)
    with pytest.raises(RuntimeError, match="group 1 failed"):
        _run(monkeypatch, paths)
    assert _current(paths) == before
    assert old_result.read_bytes() == old_contents


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
    heatmap_range = require_heatmap_range(config.part.groups[0])
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


def test_group_req_013_s01(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths)
    before = _current(paths)
    _run(monkeypatch, paths)
    after = _current(paths)
    assert all(before[key] != after[key] for key in before)
    assert all((paths.results("XX") / value).is_dir() for value in after.values())


def test_group_req_013_s02(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths)
    before = _current(paths)
    _run(monkeypatch, paths, group=0)
    after = _current(paths)
    assert before[1] == after[1]
    assert before[0] != after[0]


def test_group_req_013_s03(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path)
    _run(monkeypatch, paths)
    before = _current(paths)
    monkeypatch.setattr(
        evaluation_cli,
        "publish_current",
        lambda *_args: (_ for _ in ()).throw(OSError("interrupted")),
    )
    with pytest.raises(OSError):
        _run(monkeypatch, paths)
    assert _current(paths) == before


def test_group_req_013_s04(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path)
    _run(monkeypatch, paths)
    before = _current(paths)
    monkeypatch.setattr(
        evaluation_cli,
        "cleanup_generations",
        lambda *_args: (_ for _ in ()).throw(OSError("interrupted")),
    )
    _, run = _run(monkeypatch, paths)
    assert _current(paths) != before
    assert any("cleanup deferred" in item for item in run.warnings)


@pytest.mark.parametrize("bad", ["version", "path", "missing", "symlink", "group"])
def test_group_req_013_s05(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths)
    current = paths.result_current("XX")
    payload = json.loads(current.read_text())
    if bad == "version":
        payload["version"] = 2
    elif bad == "path":
        payload["groups"]["0"] = "../outside"
    elif bad == "missing":
        payload["groups"]["0"] = "generations/" + "0" * 32 + "/group_0"
    elif bad == "group":
        payload["groups"]["9"] = payload["groups"].pop("0")
    else:
        current.unlink()
        outside = tmp_path / "outside.json"
        outside.write_text("outside")
        current.symlink_to(outside)
    if bad != "symlink":
        current.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        read_current(paths, "XX", allowed_group_ids={0, 1})
    with pytest.raises(ValueError):
        _run(monkeypatch, paths, group=0)


def test_group_req_013_s06() -> None:
    app = typer.Typer()
    app.command()(_test_command)
    result = CliRunner().invoke(app, ["--model", "XX", "--restart"])
    assert result.exit_code != 0
    assert "restart" in result.output


def test_group_req_013_s07(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path, two=True)
    current = paths.result_current("XX")
    current.parent.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text("safe")
    current.symlink_to(outside)
    _run(monkeypatch, paths)
    assert not current.is_symlink()
    assert outside.read_text() == "safe"
    assert set(_current(paths)) == {0, 1}


def test_group_req_013_s08(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path)
    current = paths.result_current("XX")
    current.parent.mkdir(parents=True)
    current.write_text("invalid")
    monkeypatch.chdir(tmp_path)
    from app.common.cli import _run as execute

    execute("check", "XX", lambda _paths, _recorder: "ok")
    assert current.read_text() == "invalid"


def test_group_req_013_s09(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path, two=True)
    _run(monkeypatch, paths)
    before = _current(paths)
    _run(monkeypatch, paths, group=0)
    after = _current(paths)
    assert not (paths.results("XX") / before[0]).exists()
    assert (paths.results("XX") / before[1]).exists()
    assert sorted(
        path.name for path in paths.result_generations("XX").iterdir()
    ) == sorted({Path(value).parts[1] for value in after.values()})


def test_group_req_013_s10(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, paths = project(tmp_path)
    _run(monkeypatch, paths)
    orphan = create_generation(paths, "XX") / "group_0"
    orphan.mkdir()
    monkeypatch.chdir(tmp_path)
    from app.common.cli import _run as execute

    execute("check", "XX", lambda _paths, _recorder: "ok")
    assert not orphan.exists()


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
    assert effective_threshold(group, 0.4) == 0.4


def test_group_req_018_s02(tmp_path: Path) -> None:
    config, _ = project(tmp_path)
    assert config.part.groups[0].inspection_threshold is None
    assert effective_threshold(config.part.groups[0], 0.4) == 0.4


def test_group_req_018_s03(tmp_path: Path) -> None:
    config, _ = project(tmp_path)
    group = config.part.groups[0]
    group.inspection_threshold = 0.7
    assert effective_threshold(group, 0.4) == 0.7
    assert group.optuna_settings.threshold.value == 0.4


@pytest.mark.parametrize("value", [0.0, 1.0])
def test_group_req_018_s04(tmp_path: Path, value: float) -> None:
    config, _ = project(tmp_path)
    group = config.part.groups[0]
    group.inspection_threshold = value
    assert effective_threshold(group, 0.4) == value
    image = np.zeros((4, 4, 3), dtype=np.uint8)
    split = evaluate_split(
        image_path=Path("input.png"),
        image=image,
        prediction=Prediction(value, np.zeros((4, 4), dtype=np.float32)),
        split_id=0,
        threshold=value,
        heatmap_range=require_heatmap_range(group),
        result_path=tmp_path / "result.png",
    )
    assert split.status == "anomaly"
    assert split.score == value


@pytest.mark.parametrize("value", [-0.1, 1.1, "bad", True])
def test_group_req_018_s05(tmp_path: Path, value: object) -> None:
    _, paths = project(tmp_path)
    payload = json.loads(paths.model_config("XX").read_text())
    payload["groups"][0]["inspection_threshold"] = value
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
    scale = require_heatmap_range(group)
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
        heatmap_range=scale,
        result_path=tmp_path / "first.png",
    )
    second_result = evaluate_split(
        image_path=Path("input.png"),
        image=image,
        prediction=Prediction(0.8, first),
        split_id=0,
        threshold=0.4,
        heatmap_range=changed_scale,
        result_path=tmp_path / "second.png",
    )
    assert (first_result.score, first_result.status) == (
        second_result.score,
        second_result.status,
    )


def test_command_progress_non_tty_once_per_source(
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


def test_command_progress_tty_once_per_source(
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


def test_command_progress_counts_undetermined(
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


@pytest.mark.parametrize("failure", ["later_group", "final_write", "publish"])
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
    before = _current(paths)
    old_result = paths.results("XX") / before[1] / "sample.png.json"
    old_bytes = old_result.read_bytes()

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
            if output.parent.name == "group_1" and result.source_image == "second.png":
                writes += 1
                if writes == 2:
                    raise OSError("injected final write failure")
            return original_write(result, output)

        monkeypatch.setattr(evaluation.InspectionResult, "write_json", fail_final_write)
        reason = "injected final write failure"
    else:

        def fail_publish(*_args):
            raise OSError("injected publish failure")

        monkeypatch.setattr(evaluation_cli, "publish_current", fail_publish)
        reason = "injected publish failure"

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
    assert _current(paths) == before
    assert old_result.read_bytes() == old_bytes


def test_command_progress_stops_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = _two_sources(tmp_path)
    _run(monkeypatch, paths)
    before = _current(paths)
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
    assert _current(paths) == before


def test_command_progress_stops_before_failed_result_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _two_sources(tmp_path)
    _run(monkeypatch, paths)
    before = _current(paths)
    write_result = evaluation.write_inspection_result

    def fail_second_result(result, output):
        if output.parent.name == "group_1" and result.source_image == "second.png":
            raise OSError("injected result write failure")
        write_result(result, output)

    monkeypatch.setattr(evaluation, "write_inspection_result", fail_second_result)
    capsys.readouterr()
    with pytest.raises(RuntimeError, match="group 1 failed"):
        _run(monkeypatch, paths)
    stderr = capsys.readouterr().err
    assert stderr.count("検査進捗 1/2") == 1
    assert "検査進捗 2/2" not in stderr
    assert _current(paths) == before


@pytest.mark.parametrize("failure", ["final_write", "publish"])
def test_command_progress_stops_before_failed_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: str,
) -> None:
    paths = _two_sources(tmp_path)
    _run(monkeypatch, paths)
    before = _current(paths)
    if failure == "final_write":
        original = evaluation.InspectionResult.write_json
        writes = 0

        def fail_rewrite(result, output):
            nonlocal writes
            if output.parent.name == "group_1" and result.source_image == "second.png":
                writes += 1
                if writes == 2:
                    raise OSError("injected final write failure")
            return original(result, output)

        monkeypatch.setattr(evaluation.InspectionResult, "write_json", fail_rewrite)
    else:
        monkeypatch.setattr(
            evaluation_cli,
            "publish_current",
            lambda *_args: (_ for _ in ()).throw(OSError("injected publish failure")),
        )
    capsys.readouterr()
    with pytest.raises(OSError, match="injected"):
        _run(monkeypatch, paths)
    stderr = capsys.readouterr().err
    assert "検査進捗 1/2" in stderr
    assert "検査進捗 2/2" not in stderr
    assert _current(paths) == before


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
    payload["groups"][0]["heatmap_range"] = value
    paths.model_config("XX").write_text(json.dumps(payload))
    if value is None:
        with pytest.raises(ValueError, match="heatmap_range"):
            require_heatmap_range(load_config(tmp_path, "XX").part.groups[0])
    else:
        with pytest.raises(ValueError, match="heatmap_range"):
            load_config(tmp_path, "XX")
