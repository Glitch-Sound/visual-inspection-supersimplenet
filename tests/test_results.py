from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import write_test_image
from group_evaluation_helpers import FakePredictor, aligned, project, recorder

from app.common.config import preparation_fingerprint
from app.common.contracts import (
    InspectionResult,
    ResultStatus,
    SplitResult,
    load_preparation_manifest,
)
from app.image_preparation.preparation import prepare_testing
from app.model_evaluation.evaluation import evaluate_model
from app.model_evaluation.results import aggregate_status


def _evaluate(config, paths, *, group=0, score=0.5, name="one"):
    run = recorder()
    run.groups = [group]
    return evaluate_model(
        config,
        config.part.select_groups(group)[0],
        paths,
        predictor=FakePredictor(score=score),
        output_dir=paths.results("XX") / name,
        finish_runtime=lambda: run.finish(0),
    )


def test_group_req_011_s01() -> None:
    status, _ = aggregate_status(
        [
            SplitResult(
                split_id=0, image="a.png", score=0.8, status=ResultStatus.ANOMALY
            )
        ],
        required_split_ids={0, 1},
    )
    assert status == ResultStatus.ANOMALY


def test_group_req_011_s02() -> None:
    status, _ = aggregate_status(
        [SplitResult(split_id=0, image="a.png", score=0.1, status=ResultStatus.NORMAL)],
        required_split_ids={0},
    )
    assert status == ResultStatus.NORMAL


def test_group_req_011_s03() -> None:
    status, next_action = aggregate_status([], required_split_ids={0})
    assert status == ResultStatus.UNDETERMINED
    assert next_action is not None


def test_inference_failure_is_recorded_per_split(tmp_path: Path) -> None:
    config, paths = project(tmp_path)
    run = recorder()
    run.groups = [0]

    def fail_prediction(_image):
        raise RuntimeError("injected inference failure")

    result = evaluate_model(
        config,
        config.part.groups[0],
        paths,
        predictor=fail_prediction,
        output_dir=paths.results("XX") / "failed_inference",
        finish_runtime=lambda: run.finish(0),
    )[0]
    assert result.overall_status == ResultStatus.UNDETERMINED
    assert all(split.status == ResultStatus.ERROR for split in result.splits)
    assert all(split.score is None for split in result.splits)


def test_group_req_011_s04(tmp_path: Path) -> None:
    config, paths = project(tmp_path, two=True)
    first = _evaluate(config, paths, group=0, score=0.1, name="first")[0]
    second = _evaluate(config, paths, group=1, score=0.9, name="second")[0]
    assert first.overall_status == "normal"
    assert second.overall_status == "anomaly"
    assert not (paths.results("XX") / "overall.json").exists()


def test_group_req_012_s01(tmp_path: Path) -> None:
    config, paths = project(tmp_path)
    result = _evaluate(config, paths)[0]
    saved = InspectionResult.read_json(paths.results("XX") / "one" / "sample.png.json")
    assert saved.group == 0
    assert saved.range_ids == [0, 1]
    assert saved.heatmap_range == result.heatmap_range
    assert len(saved.splits) == 2


def test_group_req_012_s02(tmp_path: Path) -> None:
    config, paths = project(tmp_path)
    _evaluate(config, paths)
    path = paths.results("XX") / "one" / "sample.png.json"
    payload = json.loads(path.read_text())
    payload["overall_status"] = "unknown"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="overall_status"):
        InspectionResult.read_json(path)


def test_group_req_012_s03(tmp_path: Path) -> None:
    config, paths = project(tmp_path)
    write_test_image(paths.original_test("XX") / "sample.jpg", size=32)
    prepare_testing(config, paths, aligner=aligned)
    results = _evaluate(config, paths)
    assert len(results) == 2
    target = paths.results("XX") / "one"
    assert (target / "sample.png.json").is_file()
    assert (target / "sample.jpg.json").is_file()


def test_group_req_012_s04(tmp_path: Path) -> None:
    config, paths = project(tmp_path)
    prepared = paths.prepared_test("XX")
    image = prepared / "sample_00.png"
    image.unlink()
    image.symlink_to(paths.original_test("XX") / "sample.png")
    with pytest.raises(ValueError, match="symlink"):
        load_preparation_manifest(
            prepared,
            model="XX",
            allowed_split_ids={0, 1},
            fingerprint=preparation_fingerprint(config),
        )


def test_group_req_012_s05(tmp_path: Path) -> None:
    config, paths = project(tmp_path, two=True)
    first = _evaluate(config, paths, group=0, name="first")[0]
    second = _evaluate(config, paths, group=1, name="second")[0]
    assert first.group == 0 and second.group == 1
    assert (paths.results("XX") / "first" / "sample_00.png_result.png").is_file()
    assert (paths.results("XX") / "second" / "sample_00.png_result.png").is_file()


def test_group_req_012_s06(tmp_path: Path) -> None:
    config, paths = project(tmp_path)
    config.image_size = 9
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        _evaluate(config, paths)
