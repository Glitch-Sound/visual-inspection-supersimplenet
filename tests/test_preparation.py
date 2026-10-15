from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest
import typer
from conftest import build_project, write_test_image
from pydantic import ValidationError

from app.common.config import load_config, preparation_fingerprint
from app.common.contracts import AlignmentResult, load_preparation_manifest
from app.common.image_io import ImageReadError
from app.image_preparation.imaging import AlignedImage, AlignmentError, align_orb
from app.image_preparation.preparation import (
    PreparationError,
    create_check_image,
    prepare_testing,
    prepare_training,
)


def aligned(
    image: np.ndarray, _reference: np.ndarray, _settings: object
) -> AlignedImage:
    return AlignedImage(image, 20, 0.8, 0.0)


def _two_groups(root: Path):
    config, paths = build_project(
        root,
        ranges=[{"id": 0, "x": 0, "y": 0}, {"id": 1, "x": 8, "y": 0}],
    )
    path = paths.model_config("XX")
    payload = json.loads(path.read_text())
    second = json.loads(json.dumps(payload["groups"][0]))
    second["id"] = 1
    second["range_ids"] = [0]
    payload["groups"].append(second)
    payload["group_detail"]["1"] = json.loads(json.dumps(payload["group_detail"]["0"]))
    path.write_text(json.dumps(payload))
    return load_config(root, "XX"), paths


def _train_images(paths) -> None:
    for name in ("base.png", "a.png", "b.png"):
        write_test_image(paths.original_train("XX") / name, size=32)


def _alignment_config(paths, **changes):
    path = paths.model_config("XX")
    payload = json.loads(path.read_text())
    payload["alignment"].update(changes)
    path.write_text(json.dumps(payload))
    return load_config(paths.root, "XX")


def test_similarity_replicate_testing_pixels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, paths = build_project(tmp_path)
    config = _alignment_config(
        paths, transform_model="similarity", border_mode="replicate"
    )
    texture = np.random.default_rng(10).integers(
        20, 240, size=(128, 128, 3), dtype=np.uint8
    )
    paths.original_train("XX").mkdir(parents=True)
    paths.original_test("XX").mkdir(parents=True)
    cv2.imwrite(str(paths.original_train("XX") / "base.png"), texture)
    cv2.imwrite(str(paths.original_test("XX") / "sample.png"), texture)

    def estimate(source, *_args, **_kwargs):
        matrix = np.array([[1, 0, 9], [0, 1, 0]], dtype=np.float64)
        return matrix, np.ones((len(source), 1), dtype=np.uint8)

    monkeypatch.setattr(cv2, "estimateAffinePartial2D", estimate)
    manifest = prepare_testing(config, paths, aligner=align_orb)
    result = cv2.imread(str(paths.prepared_test("XX") / "sample_00.png"))
    assert result is not None
    np.testing.assert_array_equal(result, texture[:8, :1].repeat(8, axis=1))
    assert manifest.sources[0].alignment.inlier_reprojection_rmse_px == pytest.approx(9)


def test_alignment_estimation_failure_excludes_training(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path)
    _train_images(paths)

    def fail(_image, _reference, _settings):
        raise AlignmentError("similarity_failed", matches=20)

    manifest = prepare_training(config, paths, aligner=fail)[0]
    assert all(
        source.alignment.reason == "similarity_failed" for source in manifest.sources
    )
    assert all(not source.splits for source in manifest.sources)


def test_alignment_estimation_failure_undetermines_testing(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path)
    _train_images(paths)
    write_test_image(paths.original_test("XX") / "sample.png", size=32)

    def fail(_image, _reference, _settings):
        raise AlignmentError("no_inliers", matches=20)

    manifest = prepare_testing(config, paths, aligner=fail)
    source = manifest.sources[0]
    assert source.alignment.status == "undetermined"
    assert source.alignment.reason == "no_inliers"
    assert source.alignment.recapture_required
    assert not source.splits


def test_alignment_options_change_fingerprint(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path)
    _train_images(paths)
    write_test_image(paths.original_test("XX") / "sample.png", size=32)
    prepare_training(config, paths, aligner=aligned)
    prepare_testing(config, paths, aligner=aligned)
    for field, value in (
        ("transform_model", "similarity"),
        ("border_mode", "replicate"),
    ):
        changed = _alignment_config(paths, **{field: value})
        with pytest.raises(ValueError, match="fingerprint mismatch"):
            load_preparation_manifest(
                paths.prepared_train("XX", 0),
                model="XX",
                group=0,
                allowed_split_ids={0},
                fingerprint=preparation_fingerprint(
                    changed, group=changed.part.groups[0]
                ),
            )
        with pytest.raises(ValueError, match="fingerprint mismatch"):
            load_preparation_manifest(
                paths.prepared_test("XX"),
                model="XX",
                allowed_split_ids={0},
                fingerprint=preparation_fingerprint(changed),
            )


def test_training_alignment_rmse_manifest(tmp_path: Path) -> None:
    config, paths = _two_groups(tmp_path)
    for name, value in (("base.png", 50), ("a.png", 80), ("b.png", 100)):
        write_test_image(paths.original_train("XX") / name, size=32, value=value)

    def measured(image, _reference, _settings):
        return AlignedImage(image, 20, 0.8, float(image[0, 0, 0]) / 100)

    manifests = prepare_training(config, paths, aligner=measured)
    for name, expected in (("base.png", 0.5), ("a.png", 0.8), ("b.png", 1.0)):
        assert [
            next(
                s for s in manifests[group].sources if s.source_image == name
            ).alignment.inlier_reprojection_rmse_px
            for group in manifests
        ] == [expected, expected]
    saved = json.loads((paths.prepared_train("XX", 0) / "manifest.json").read_text())
    assert (
        len(
            [
                s
                for s in saved["sources"]
                if s["alignment"]["inlier_reprojection_rmse_px"] is not None
            ]
        )
        == 3
    )


def test_testing_alignment_rmse_manifest(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path)
    write_test_image(paths.original_train("XX") / "base.png", size=32)
    write_test_image(paths.original_test("XX") / "a.png", size=32, value=50)
    write_test_image(paths.original_test("XX") / "b.png", size=32, value=100)

    def measured(image, _reference, _settings):
        return AlignedImage(image, 20, 0.8, float(image[0, 0, 0]) / 100)

    prepare_testing(config, paths, aligner=measured)
    saved = json.loads((paths.prepared_test("XX") / "manifest.json").read_text())
    assert {
        s["source_image"]: s["alignment"]["inlier_reprojection_rmse_px"]
        for s in saved["sources"]
    } == {"a.png": 0.5, "b.png": 1.0}


def test_failed_alignment_rmse_is_null(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path)
    _train_images(paths)
    write_test_image(paths.original_test("XX") / "sample.png", size=32)

    def fail(_image, _reference, _settings):
        raise AlignmentError("no_inliers")

    train = prepare_training(config, paths, aligner=fail)[0]
    testing = prepare_testing(config, paths, aligner=fail)
    for source in [*train.sources, *testing.sources]:
        assert source.alignment.inlier_reprojection_rmse_px is None
        assert not source.splits
    for invalid in (-1, float("nan"), float("inf")):
        with pytest.raises(ValidationError):
            AlignmentResult(status="aligned", inlier_reprojection_rmse_px=invalid)


def test_group_req_001_s01(tmp_path: Path) -> None:
    config, paths = _two_groups(tmp_path)
    _train_images(paths)
    assert create_check_image(config, paths) == paths.check_image("XX")
    assert paths.check_image("XX").is_file()
    assert paths.check_image("XX", 0).is_file()
    assert paths.check_image("XX", 1).is_file()
    assert (tmp_path / "data/03_check/XX/group_00.png").is_file()
    assert (tmp_path / "data/03_check/XX/group_01.png").is_file()


def test_group_req_001_s02(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path, ranges=[{"id": 0, "x": 30, "y": 0}])
    _train_images(paths)
    with pytest.raises(ValueError, match="range|bounds|image"):
        create_check_image(config, paths)
    assert not paths.check_image("XX").exists()


def test_group_req_001_s03(tmp_path: Path) -> None:
    _, paths = build_project(tmp_path)
    payload = json.loads(paths.model_config("XX").read_text())
    payload["base"] = "../outside.png"
    paths.model_config("XX").write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="base"):
        load_config(tmp_path, "XX")


def test_group_req_001_s04(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config, paths = build_project(
        tmp_path,
        image_size=500,
        ranges=[{"id": 0, "x": 400, "y": 0}, {"id": 1, "x": 401, "y": 0}],
    )
    (tmp_path / "config" / "setting.ini").write_text(
        "[IMAGE]\nSIZE = 500\nRESIZE = 0.5\n"
    )
    config = load_config(tmp_path, "XX")
    write_test_image(paths.original_train("XX") / "base.png", size=1500)
    captured = []
    from app.image_preparation import preparation

    original = preparation.draw_ranges

    def capture(image, ranges, size):
        captured.extend(ranges)
        return original(image, ranges, size)

    monkeypatch.setattr(preparation, "draw_ranges", capture)
    create_check_image(config, paths)
    assert [item.x for item in captured[:2]] == [200, 201]


def test_group_req_001_s05(tmp_path: Path) -> None:
    config, paths = _two_groups(tmp_path)
    _train_images(paths)
    create_check_image(config, paths)
    assert (
        paths.check_image("XX", 0).read_bytes()
        != paths.check_image("XX", 1).read_bytes()
    )


def test_group_req_002_s01(tmp_path: Path) -> None:
    config, paths = _two_groups(tmp_path)
    _train_images(paths)
    result = prepare_training(config, paths, aligner=aligned)
    assert set(result) == {0, 1}
    assert (paths.prepared_train("XX", 0) / "a_01.png").is_file()
    assert (paths.prepared_train("XX", 1) / "a_00.png").is_file()
    assert (tmp_path / "data/04_train/XX/group_00/a_01.png").is_file()
    assert (tmp_path / "data/04_train/XX/group_01/a_00.png").is_file()


def test_group_req_002_s02(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path, blacklist=[{"image": "a.png", "id": [0]}])
    _train_images(paths)
    result = prepare_training(config, paths, aligner=aligned)[0]
    assert not (paths.prepared_train("XX", 0) / "a_00.png").exists()
    assert any(item["reason"] == "blacklist" for item in result.excluded)


def test_group_req_002_s03(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path)
    _train_images(paths)

    def fail(_image, _reference, _settings):
        raise AlignmentError("too few matches")

    result = prepare_training(config, paths, aligner=fail)[0]
    assert all(not source.splits for source in result.sources)
    assert result.excluded[0]["reason"] == "too few matches"


def test_group_req_002_s04(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path, ranges=[{"id": 0, "x": 30, "y": 0}])
    _train_images(paths)
    with pytest.raises(PreparationError, match="a.png"):
        prepare_training(config, paths, aligner=aligned)
    assert not paths.prepared_train("XX", 0).exists()


def test_group_req_002_s05(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path)
    _train_images(paths)
    prepare_training(config, paths, aligner=aligned)
    marker = paths.prepared_train("XX", 0) / "marker"
    marker.write_text("old")
    (paths.original_train("XX") / "a.png").write_bytes(b"bad image")
    with pytest.raises(ImageReadError, match="a.png"):
        prepare_training(config, paths, aligner=aligned)
    assert marker.read_text() == "old"


def test_group_req_002_s06(tmp_path: Path) -> None:
    _, paths = build_project(tmp_path)
    payload = json.loads(paths.model_config("XX").read_text())
    payload["alignment"]["knn_k"] = 3
    paths.model_config("XX").write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="knn_k"):
        load_config(tmp_path, "XX")


def test_group_req_002_s07(tmp_path: Path) -> None:
    config, paths = _two_groups(tmp_path)
    _train_images(paths)
    prepare_training(config, paths, aligner=aligned)
    marker = paths.prepared_train("XX", 1) / "marker"
    marker.write_text("preserved")
    prepare_training(config, paths, group=0, aligner=aligned)
    assert marker.read_text() == "preserved"


def test_group_req_002_s08(tmp_path: Path) -> None:
    config, paths = _two_groups(tmp_path)
    _train_images(paths)
    prepare_training(config, paths, aligner=aligned)
    assert (paths.prepared_train("XX", 0) / "a_00.png").read_bytes() == (
        paths.prepared_train("XX", 1) / "a_00.png"
    ).read_bytes()


def test_group_req_025_s01(tmp_path: Path) -> None:
    config, paths = _two_groups(tmp_path)
    _train_images(paths)
    manifest = prepare_training(config, paths, group=1, aligner=aligned)[1]
    assert manifest.group == 1
    assert manifest.range_ids == [0]
    assert manifest.preparation_fingerprint == preparation_fingerprint(
        config, group=config.part.groups[1]
    )


def test_group_req_025_s02(tmp_path: Path) -> None:
    config, paths = _two_groups(tmp_path)
    _train_images(paths)
    write_test_image(paths.original_test("XX") / "sample.png", size=32)
    manifest = prepare_testing(config, paths, aligner=aligned)
    assert {
        split.split_id for source in manifest.sources for split in source.splits
    } == {0, 1}
    assert manifest.preparation_fingerprint == preparation_fingerprint(config)


def test_req_003_s01(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path, blacklist=[{"image": "a.png", "id": [0]}])
    _train_images(paths)
    write_test_image(paths.original_test("XX") / "a.png", size=32)
    manifest = prepare_testing(config, paths, aligner=aligned)
    assert [source.source_image for source in manifest.sources] == ["a.png"]
    assert [split.image for split in manifest.sources[0].splits] == ["a_00.png"]
    assert (paths.prepared_test("XX") / "a_00.png").is_file()


def test_req_003_s02(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.image_preparation import cli as preparation_cli

    config, paths = build_project(tmp_path)
    _train_images(paths)
    write_test_image(paths.original_test("XX") / "sample.png", size=32)

    def fail(_image, _reference, _settings):
        raise AlignmentError("too few matches")

    original = prepare_testing
    monkeypatch.setattr(
        preparation_cli,
        "prepare_testing",
        lambda config, paths, **kwargs: original(config, paths, aligner=fail, **kwargs),
    )
    monkeypatch.chdir(tmp_path)
    capsys.readouterr()
    preparation_cli._test_pre_command(model="XX")
    captured = capsys.readouterr()
    assert "recapture is required" in captured.err
    assert json.loads(captured.out)["exit_code"] == 0
    saved = json.loads((paths.prepared_test("XX") / "manifest.json").read_text())
    source = saved["sources"][0]
    assert source["alignment"]["recapture_required"] is True
    assert source["source_image"] == "sample.png"
    assert source["alignment"]["status"] == "undetermined"
    assert source["alignment"]["reason"] == "too few matches"
    assert source["splits"] == []
    assert not (paths.prepared_test("XX") / "sample_00.png").exists()


def test_req_003_s03(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path, ranges=[{"id": 0, "x": 30, "y": 0}])
    _train_images(paths)
    write_test_image(paths.original_test("XX") / "sample.png", size=32)
    with pytest.raises(PreparationError, match="sample.png.*0"):
        prepare_testing(config, paths, aligner=aligned)
    assert not paths.prepared_test("XX").exists()


def test_req_003_s04(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path)
    _train_images(paths)
    write_test_image(paths.original_test("XX") / "sample.png", size=32)
    prepare_testing(config, paths, aligner=aligned)
    prepared = paths.prepared_test("XX")
    before = {path.name: path.read_bytes() for path in prepared.iterdir()}
    (paths.original_test("XX") / "sample.png").write_bytes(b"bad image")
    with pytest.raises(ImageReadError, match="sample.png"):
        prepare_testing(config, paths, aligner=aligned)
    assert {path.name: path.read_bytes() for path in prepared.iterdir()} == before


def test_req_003_s07(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.image_preparation import cli as preparation_cli

    config, paths = _two_groups(tmp_path)
    _train_images(paths)
    write_test_image(paths.original_test("XX") / "sample.png", size=32)
    prepare_testing(config, paths, aligner=aligned)
    prepared = paths.prepared_test("XX")
    other_before = (prepared / "sample_01.png").read_bytes()

    def changed(image, _reference, _settings):
        return AlignedImage(np.zeros_like(image), 20, 0.8, 0.0)

    monkeypatch.setattr(
        preparation_cli,
        "prepare_testing",
        lambda config, paths, **kwargs: prepare_testing(
            config, paths, aligner=changed, **kwargs
        ),
    )
    monkeypatch.chdir(tmp_path)
    capsys.readouterr()
    preparation_cli._test_pre_command(model="XX", group=1)
    assert json.loads(capsys.readouterr().out)["groups"] == [1]
    manifest = load_preparation_manifest(
        prepared,
        model="XX",
        allowed_split_ids={0, 1},
        fingerprint=preparation_fingerprint(config),
    )
    assert (prepared / "sample_01.png").read_bytes() == other_before
    selected_image = cv2.imread(str(prepared / "sample_00.png"))
    assert selected_image is not None
    assert selected_image.max() == 0
    assert {split.split_id for split in manifest.sources[0].splits} == {0, 1}


def test_req_003_s08(tmp_path: Path) -> None:
    config, paths = _two_groups(tmp_path)
    _train_images(paths)
    write_test_image(paths.original_test("XX") / "sample.png", size=32)
    manifest = prepare_testing(config, paths, group=1, aligner=aligned)
    assert {split.split_id for split in manifest.sources[0].splits} == {0}
    assert (paths.prepared_test("XX") / "sample_00.png").is_file()
    assert not (paths.prepared_test("XX") / "sample_01.png").exists()


def test_req_003_s09(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.image_preparation import cli as preparation_cli

    config, paths = _two_groups(tmp_path)
    _train_images(paths)
    write_test_image(paths.original_test("XX") / "sample.png", size=32)
    prepare_testing(config, paths, aligner=aligned)
    before = {
        path.name: path.read_bytes() for path in paths.prepared_test("XX").iterdir()
    }
    monkeypatch.chdir(tmp_path)
    with pytest.raises(typer.Exit) as error:
        preparation_cli._test_pre_command(model="XX", group=99)
    assert error.value.exit_code == 2
    assert {
        path.name: path.read_bytes() for path in paths.prepared_test("XX").iterdir()
    } == before


def test_req_003_s10(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.image_preparation import cli as preparation_cli

    config, paths = _two_groups(tmp_path)
    _train_images(paths)
    write_test_image(paths.original_test("XX") / "sample.png", size=32)
    prepare_testing(config, paths, aligner=aligned)
    before = {
        path.name: path.read_bytes() for path in paths.prepared_test("XX").iterdir()
    }
    (tmp_path / "config" / "setting.ini").write_text(
        "[IMAGE]\nSIZE = 8\nRESIZE = 0.5\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    capsys.readouterr()
    with pytest.raises(typer.Exit) as error:
        preparation_cli._test_pre_command(model="XX", group=1)
    captured = capsys.readouterr()
    assert error.value.exit_code == 2
    assert "fingerprint" in captured.err
    assert json.loads(captured.out)["exit_code"] == 2
    assert {
        path.name: path.read_bytes() for path in paths.prepared_test("XX").iterdir()
    } == before


@pytest.mark.parametrize("command", ["train-pre", "test-pre"])
def test_req_017_s01(
    tmp_path: Path,
    command: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from app.image_preparation import cli as preparation_cli
    from app.image_preparation import preparation

    config, paths = build_project(tmp_path)
    _train_images(paths)
    write_test_image(paths.original_test("XX") / "sample.png", size=32)
    write_test_image(paths.original_test("XX") / "second.png", size=32)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        preparation_cli,
        "prepare_training",
        lambda config, paths, **kwargs: preparation.prepare_training(
            config, paths, aligner=aligned, **kwargs
        ),
    )
    monkeypatch.setattr(
        preparation_cli,
        "prepare_testing",
        lambda config, paths, **kwargs: preparation.prepare_testing(
            config, paths, aligner=aligned, **kwargs
        ),
    )
    capsys.readouterr()
    if command == "train-pre":
        preparation_cli._train_pre_command(model="XX", group=None)
        total = 3
        summary = "学習準備完了"
    else:
        preparation_cli._test_pre_command(model="XX")
        total = 2
        summary = "試験準備完了"
    captured = capsys.readouterr()
    stderr = captured.err
    assert f"準備進捗 0/{total}" in stderr
    assert f"準備進捗 1/{total}" in stderr
    assert f"準備進捗 {total}/{total}" in stderr
    assert summary in stderr
    assert json.loads(captured.out)["exit_code"] == 0


@pytest.mark.parametrize("command", ["train-pre", "test-pre"])
def test_req_017_s02(
    tmp_path: Path,
    command: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from app.image_preparation import cli as preparation_cli
    from app.image_preparation import preparation

    config, paths = build_project(tmp_path)
    _train_images(paths)
    if command == "train-pre":
        (paths.original_train("XX") / "b.png").write_bytes(b"bad image")
    else:
        write_test_image(paths.original_test("XX") / "a.png", size=32)
        (paths.original_test("XX") / "b.png").write_bytes(b"bad image")
    total = 3 if command == "train-pre" else 2
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        preparation_cli,
        "prepare_training",
        lambda config, paths, **kwargs: preparation.prepare_training(
            config, paths, aligner=aligned, **kwargs
        ),
    )
    monkeypatch.setattr(
        preparation_cli,
        "prepare_testing",
        lambda config, paths, **kwargs: preparation.prepare_testing(
            config, paths, aligner=aligned, **kwargs
        ),
    )
    capsys.readouterr()
    with pytest.raises(typer.Exit) as error:
        if command == "train-pre":
            preparation_cli._train_pre_command(model="XX", group=None)
        else:
            preparation_cli._test_pre_command(model="XX")
    captured = capsys.readouterr()
    stderr = captured.err
    assert error.value.exit_code == 3
    assert f"準備進捗 1/{total}" in stderr
    assert f"準備進捗 {total}/{total}" not in stderr
    assert "b.png" in stderr
    assert "処理失敗" in stderr
    assert json.loads(captured.out)["exit_code"] == 3
