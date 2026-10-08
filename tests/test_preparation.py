from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import cv2
import numpy as np
import pytest
from conftest import build_project, write_test_image

from app.common.atomic import recover_directory_swap
from app.common.cli import PreparationProgress
from app.common.config import AlignmentSettings, CropRange, load_config
from app.common.image_io import ImageReadError
from app.image_preparation import cli as preparation_cli
from app.image_preparation.imaging import (
    AlignedImage,
    AlignmentError,
    align_orb,
    scaled_crop_range,
)
from app.image_preparation.preparation import (
    PreparationError,
    alignment_warning,
    create_check_image,
    prepare_testing,
    prepare_training,
)


def identity_aligner(image: np.ndarray, *_args: object) -> AlignedImage:
    return AlignedImage(image.copy(), matches=42, inlier_ratio=0.9)


def test_atomic_directory_recovers_interrupted_swap(tmp_path: Path) -> None:
    target = tmp_path / "derived"
    backup = tmp_path / ".derived.backup"
    backup.mkdir()
    (backup / "keep.txt").write_text("old", encoding="utf-8")

    returned = recover_directory_swap(target)

    assert returned == backup
    assert (target / "keep.txt").read_text(encoding="utf-8") == "old"
    assert not backup.exists()

    backup.mkdir()
    (backup / "old.txt").write_text("old", encoding="utf-8")
    recover_directory_swap(target)
    assert target.is_dir()
    assert not backup.exists()


def test_align_orb_uses_configured_ransac_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rng = np.random.default_rng(42)
    reference = rng.integers(0, 256, size=(256, 256, 3), dtype=np.uint8)
    captured: dict[str, float] = {}

    def find_homography(
        source: np.ndarray,
        target: np.ndarray,
        method: int,
        threshold: float,
        *,
        confidence: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        assert source.shape == target.shape
        assert method == cv2.RANSAC
        captured["threshold"] = threshold
        captured["confidence"] = confidence
        return np.eye(3, dtype=np.float64), np.ones((len(source), 1), dtype=np.uint8)

    monkeypatch.setattr(cv2, "findHomography", find_homography)
    settings = AlignmentSettings(
        minimum_matches=4,
        ransac_reprojection_threshold_px=2.5,
        ransac_confidence=0.9,
        minimum_inlier_ratio=0.75,
    )

    result = align_orb(reference.copy(), reference, settings)

    assert result.matches >= settings.minimum_matches
    assert result.inlier_ratio == 1.0
    assert captured == {"threshold": 2.5, "confidence": 0.9}


def test_align_orb_filters_knn_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    rng = np.random.default_rng(42)
    reference = rng.integers(0, 256, size=(256, 256, 3), dtype=np.uint8)
    captured: dict[str, object] = {}

    class Matcher:
        def knnMatch(
            self, _source: np.ndarray, _target: np.ndarray, *, k: int
        ) -> list[list[cv2.DMatch]]:
            captured["k"] = k
            return [
                [cv2.DMatch(i, i, 0, 10), cv2.DMatch(i, i + 1, 0, 20)]
                for i in range(10)
            ] + [
                [cv2.DMatch(10, 10, 0, 15), cv2.DMatch(10, 11, 0, 20)],
                [cv2.DMatch(11, 11, 0, 10)],
            ]

    def matcher_factory(norm: int, *, crossCheck: bool) -> Matcher:
        assert norm == cv2.NORM_HAMMING
        captured["cross_check"] = crossCheck
        return Matcher()

    def find_homography(
        source: np.ndarray,
        _target: np.ndarray,
        _method: int,
        _threshold: float,
        *,
        confidence: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        assert confidence == 0.95
        captured["points"] = len(source)
        return np.eye(3), np.ones((len(source), 1), dtype=np.uint8)

    monkeypatch.setattr(cv2, "BFMatcher", matcher_factory)
    monkeypatch.setattr(cv2, "findHomography", find_homography)
    result = align_orb(reference.copy(), reference, AlignmentSettings())
    assert result.matches == 10
    assert captured == {"k": 2, "cross_check": False, "points": 10}
    with pytest.raises(AlignmentError, match="insufficient_matches") as error:
        align_orb(
            reference.copy(),
            reference,
            AlignmentSettings(minimum_matches=11),
        )
    assert error.value.matches == 10


def test_check_uses_resized_reference_and_original_crop_size(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path, image_size=8)
    config = config.model_copy(update={"image_resize": 0.5})
    write_test_image(paths.original_train("XX") / "base.png", size=32)
    output = cv2.imread(str(create_check_image(config, paths)))
    assert output is not None
    assert output.shape == (16, 16, 3)
    assert np.all(output[0, 0] == (0, 0, 255))


def test_train_pre_resizes_before_alignment_and_keeps_crop_size(
    tmp_path: Path,
) -> None:
    config, paths = build_project(tmp_path, image_size=8)
    config = config.model_copy(update={"image_resize": 0.5})
    write_test_image(paths.original_train("XX") / "base.png", size=32)
    dimensions: list[tuple[tuple[int, ...], tuple[int, ...]]] = []

    def aligner(
        image: np.ndarray, reference: np.ndarray, _settings: object
    ) -> AlignedImage:
        dimensions.append((image.shape, reference.shape))
        return identity_aligner(image)

    prepare_training(config, paths, aligner=aligner)
    assert dimensions == [((16, 16, 3), (16, 16, 3))]
    split = cv2.imread(str(paths.prepared_train("XX") / "base_00.png"))
    assert split is not None and split.shape == (8, 8, 3)


def test_test_pre_resizes_before_alignment_and_keeps_crop_size(
    tmp_path: Path,
) -> None:
    config, paths = build_project(tmp_path, image_size=8)
    config = config.model_copy(update={"image_resize": 0.5})
    write_test_image(paths.original_train("XX") / "base.png", size=32)
    write_test_image(paths.original_test("XX") / "sample.png", size=32)
    dimensions: list[tuple[tuple[int, ...], tuple[int, ...]]] = []

    def aligner(
        image: np.ndarray, reference: np.ndarray, _settings: object
    ) -> AlignedImage:
        dimensions.append((image.shape, reference.shape))
        return identity_aligner(image)

    prepare_testing(config, paths, aligner=aligner)
    assert dimensions == [((16, 16, 3), (16, 16, 3))]
    split = cv2.imread(str(paths.prepared_test("XX") / "sample_00.png"))
    assert split is not None and split.shape == (8, 8, 3)


def test_train_pre_read_failure_preserves_existing_output(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path)
    write_test_image(paths.original_train("XX") / "base.png")
    (paths.original_train("XX") / "broken.png").write_bytes(b"broken")
    target = paths.prepared_train("XX")
    target.mkdir(parents=True)
    (target / "keep.txt").write_text("old", encoding="utf-8")
    with pytest.raises(ImageReadError, match="broken.png"):
        prepare_training(config, paths, aligner=identity_aligner)
    assert (target / "keep.txt").read_text(encoding="utf-8") == "old"


def test_test_pre_read_failure_preserves_existing_output(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path)
    write_test_image(paths.original_train("XX") / "base.png")
    source = paths.original_test("XX")
    source.mkdir(parents=True)
    (source / "broken.png").write_bytes(b"broken")
    target = paths.prepared_test("XX")
    target.mkdir(parents=True)
    (target / "keep.txt").write_text("old", encoding="utf-8")
    with pytest.raises(ImageReadError, match="broken.png"):
        prepare_testing(config, paths, aligner=identity_aligner)
    assert (target / "keep.txt").read_text(encoding="utf-8") == "old"


def test_check_writes_labeled_ranges(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path, ranges=[{"id": 7, "x": 2, "y": 3}])
    write_test_image(paths.original_train("XX") / "base.png")
    target = create_check_image(config, paths)
    output = cv2.imread(str(target))
    assert output is not None
    assert np.any((output[:, :, 2] > 200) & (output[:, :, 1] < 80))


def test_train_pre_aligns_and_crops_images(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path)
    original = write_test_image(paths.original_train("XX") / "base.png")
    write_test_image(paths.original_train("XX") / "normal.png", value=100)
    before = original.copy()
    manifest = prepare_training(config, paths, aligner=identity_aligner)
    assert len(manifest.sources) == 2
    assert all(
        source.splits[0].image.endswith("_00.png") for source in manifest.sources
    )
    restored = cv2.imread(str(paths.original_train("XX") / "base.png"))
    assert restored is not None
    assert np.array_equal(restored, before)


def test_train_pre_excludes_blacklist_entries(tmp_path: Path) -> None:
    config, paths = build_project(
        tmp_path, blacklist=[{"image": "normal.png", "id": [0]}]
    )
    write_test_image(paths.original_train("XX") / "base.png")
    write_test_image(paths.original_train("XX") / "normal.png")
    manifest = prepare_training(config, paths, aligner=identity_aligner)
    normal = next(
        item for item in manifest.sources if item.source_image == "normal.png"
    )
    assert normal.splits == []
    assert any(item.get("reason") == "blacklist" for item in manifest.excluded)


@pytest.mark.parametrize(
    "reason", ["insufficient_matches", "homography_failed", "insufficient_inlier_ratio"]
)
def test_train_pre_warns_and_skips_alignment_failure(
    tmp_path: Path, reason: str
) -> None:
    config, paths = build_project(tmp_path)
    write_test_image(paths.original_train("XX") / "base.png")

    def fail(*_args: object) -> AlignedImage:
        raise AlignmentError(reason, matches=3, inlier_ratio=0.1)

    manifest = prepare_training(config, paths, aligner=fail)
    assert manifest.sources[0].splits == []
    assert manifest.sources[0].alignment.reason == reason
    assert manifest.excluded[0]["reason"] == reason


def test_train_pre_rejects_out_of_bounds_crop_atomically(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path, ranges=[{"id": 0, "x": 20, "y": 20}])
    write_test_image(paths.original_train("XX") / "base.png")
    target = paths.prepared_train("XX")
    target.mkdir(parents=True)
    sentinel = target / "keep.txt"
    sentinel.write_text("old", encoding="utf-8")
    with pytest.raises(PreparationError, match="outside image bounds"):
        prepare_training(config, paths, aligner=identity_aligner)
    assert sentinel.read_text(encoding="utf-8") == "old"


def test_test_pre_does_not_apply_blacklist(tmp_path: Path) -> None:
    config, paths = build_project(
        tmp_path, blacklist=[{"image": "sample.png", "id": [0]}]
    )
    write_test_image(paths.original_train("XX") / "base.png")
    write_test_image(paths.original_test("XX") / "sample.png")
    manifest = prepare_testing(config, paths, aligner=identity_aligner)
    assert len(manifest.sources[0].splits) == 1


@pytest.mark.parametrize(
    "reason", ["insufficient_matches", "homography_failed", "insufficient_inlier_ratio"]
)
def test_test_pre_carries_alignment_failure(tmp_path: Path, reason: str) -> None:
    config, paths = build_project(tmp_path)
    write_test_image(paths.original_train("XX") / "base.png")
    write_test_image(paths.original_test("XX") / "sample.png")

    def fail(*_args: object) -> AlignedImage:
        raise AlignmentError(reason)

    manifest = prepare_testing(config, paths, aligner=fail)
    assert manifest.sources[0].alignment.status == "undetermined"
    assert manifest.sources[0].alignment.reason == reason


def test_test_pre_rejects_out_of_bounds_crop(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path, ranges=[{"id": 0, "x": 30, "y": 0}])
    write_test_image(paths.original_train("XX") / "base.png")
    write_test_image(paths.original_test("XX") / "sample.png")
    with pytest.raises(PreparationError, match="outside image bounds"):
        prepare_testing(config, paths, aligner=identity_aligner)
    assert not paths.prepared_test("XX").exists()


@pytest.mark.parametrize("testing", [False, True])
def test_crop_error_identifies_source_and_split(tmp_path: Path, testing: bool) -> None:
    config, paths = build_project(tmp_path, ranges=[{"id": 7, "x": 30, "y": 0}])
    write_test_image(paths.original_train("XX") / "base.png")
    prepare = prepare_testing if testing else prepare_training
    if testing:
        write_test_image(paths.original_test("XX") / "sample.png")
        expected_source = "sample.png"
    else:
        expected_source = "base.png"

    with pytest.raises(PreparationError) as captured:
        prepare(config, paths, aligner=identity_aligner)

    message = str(captured.value)
    assert expected_source in message
    assert "range id 7" in message


def test_alignment_warning_identifies_source_reason_and_action() -> None:
    training = alignment_warning("train.png", "insufficient_matches", testing=False)
    testing = alignment_warning("test.png", "homography_failed", testing=True)

    assert "train.png" in training
    assert "insufficient_matches" in training
    assert "manual review is required" in training
    assert "test.png" in testing
    assert "homography_failed" in testing
    assert "undetermined" in testing
    assert "recapture is required" in testing


def test_change_req_001_01(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path, ranges=[{"id": 3, "x": 4, "y": 6}])
    write_test_image(paths.original_train("XX") / "base.png", size=32)
    output = cv2.imread(str(create_check_image(config, paths)))
    assert output is not None and output.shape == (32, 32, 3)
    assert tuple(output[6, 4]) == (0, 0, 255)


def test_change_req_001_02(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path, ranges=[{"id": 3, "x": 32, "y": 0}])
    write_test_image(paths.original_train("XX") / "base.png")
    with pytest.raises(ValueError, match="range id 3.*outside image bounds"):
        create_check_image(config, paths)
    assert not paths.check_image("XX").exists()


def test_change_req_001_03(tmp_path: Path) -> None:
    _config, paths = build_project(tmp_path)
    payload = json.loads(paths.model_config("XX").read_text())
    payload["base"] = "../outside.png"
    paths.model_config("XX").write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="base"):
        load_config(tmp_path, "XX")


@pytest.mark.parametrize(
    ("command", "output_name"),
    [
        (preparation_cli._check_command, "check_image"),
        (preparation_cli._train_pre_command, "prepared_train"),
        (preparation_cli._test_pre_command, "prepared_test"),
    ],
)
def test_base_symlink_outside_model_root_is_rejected_before_preparation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: Any,
    output_name: str,
) -> None:
    _config, paths = build_project(tmp_path)
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"outside unchanged")
    base = paths.original_train("XX") / "base.png"
    base.parent.mkdir(parents=True, exist_ok=True)
    try:
        base.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")

    output = getattr(paths, output_name)("XX")
    if output.is_dir() or output_name != "check_image":
        output.mkdir(parents=True, exist_ok=True)
        old_artifact = output / "manifest.json"
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        old_artifact = output
    old_artifact.write_bytes(b"old unchanged")
    monkeypatch.setattr(
        preparation_cli,
        "_run",
        lambda _name, _model, action: action(paths, None),
    )
    monkeypatch.setattr(
        "app.image_preparation.preparation.read_image",
        lambda _path: pytest.fail("image must not be read"),
    )

    with pytest.raises(ValueError, match="path escapes managed root"):
        command(model="XX")
    assert outside.read_bytes() == b"outside unchanged"
    assert old_artifact.read_bytes() == b"old unchanged"


def test_change_req_001_04(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config, paths = build_project(
        tmp_path,
        image_size=500,
        ranges=[{"id": 1, "x": 400, "y": 0}, {"id": 2, "x": 401, "y": 0}],
    )
    config = config.model_copy(update={"image_resize": 0.5})
    write_test_image(paths.original_train("XX") / "base.png", size=1500)
    reference = np.zeros((750, 750, 3), dtype=np.uint8)
    assert scaled_crop_range(reference, CropRange(id=1, x=400, y=0), 500, 0.5).x == 200
    assert scaled_crop_range(reference, CropRange(id=2, x=401, y=0), 500, 0.5).x == 201
    rectangles: list[tuple[tuple[int, int], tuple[int, int]]] = []
    labels: list[str] = []
    original_rectangle = cv2.rectangle
    original_put_text = cv2.putText

    def record_rectangle(
        image: np.ndarray,
        start: tuple[int, int],
        end: tuple[int, int],
        color: tuple[int, int, int],
        thickness: int,
    ) -> np.ndarray:
        rectangles.append((start, end))
        return original_rectangle(image, start, end, color, thickness)

    def record_label(image: np.ndarray, label: str, *args: object) -> np.ndarray:
        labels.append(label)
        return cast(np.ndarray, cast(Any, original_put_text)(image, label, *args))

    monkeypatch.setattr(cv2, "rectangle", record_rectangle)
    monkeypatch.setattr(cv2, "putText", record_label)
    output = cv2.imread(str(create_check_image(config, paths)))
    assert output is not None and output.shape == (750, 750, 3)
    assert rectangles == [((200, 0), (699, 499)), ((201, 0), (700, 499))]
    assert labels == ["01", "02"]


def test_change_req_002_01(tmp_path: Path) -> None:
    config, paths = build_project(
        tmp_path, image_size=8, ranges=[{"id": 0, "x": 8, "y": 10}]
    )
    config = config.model_copy(update={"image_resize": 0.5})
    write_test_image(paths.original_train("XX") / "base.png", size=32)
    manifest = prepare_training(config, paths, aligner=identity_aligner)
    original = cv2.imread(str(paths.original_train("XX") / "base.png"))
    split = cv2.imread(str(paths.prepared_train("XX") / "base_00.png"))
    assert original is not None and split is not None
    expected = cv2.resize(original, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    assert np.array_equal(split, expected[5:13, 4:12])
    assert manifest.sources[0].splits[0].split_id == 0


def test_change_req_002_02(tmp_path: Path) -> None:
    config, paths = build_project(
        tmp_path, blacklist=[{"image": "base.png", "id": [0]}]
    )
    write_test_image(paths.original_train("XX") / "base.png")
    manifest = prepare_training(config, paths, aligner=identity_aligner)
    assert manifest.sources[0].splits == []
    assert not (paths.prepared_train("XX") / "base_00.png").exists()


def test_change_req_002_03(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path)
    write_test_image(paths.original_train("XX") / "base.png")

    def fail(*_args: object) -> AlignedImage:
        raise AlignmentError("insufficient_matches")

    manifest = prepare_training(config, paths, aligner=fail)
    assert manifest.sources[0].splits == []
    assert manifest.excluded[0]["reason"] == "insufficient_matches"


def test_change_req_002_04(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path, ranges=[{"id": 7, "x": 40, "y": 0}])
    write_test_image(paths.original_train("XX") / "base.png")
    with pytest.raises(PreparationError, match="base.png: range id 7"):
        prepare_training(config, paths, aligner=identity_aligner)
    assert not paths.prepared_train("XX").exists()


def test_change_req_002_05(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path)
    write_test_image(paths.original_train("XX") / "base.png")
    (paths.original_train("XX") / "broken.png").write_bytes(b"broken")
    target = paths.prepared_train("XX")
    target.mkdir(parents=True)
    (target / "keep").write_bytes(b"old")
    with pytest.raises(ImageReadError, match="broken.png"):
        prepare_training(config, paths, aligner=identity_aligner)
    assert (target / "keep").read_bytes() == b"old"


def test_change_req_002_06(tmp_path: Path) -> None:
    _config, paths = build_project(tmp_path)
    payload = json.loads(paths.model_config("XX").read_text())
    payload["alignment"]["ratio_threshold"] = 1
    paths.model_config("XX").write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="ratio_threshold"):
        load_config(tmp_path, "XX")


def test_change_req_003_01(tmp_path: Path) -> None:
    config, paths = build_project(
        tmp_path,
        image_size=8,
        ranges=[{"id": 0, "x": 8, "y": 10}],
        blacklist=[{"image": "sample.png", "id": [0]}],
    )
    config = config.model_copy(update={"image_resize": 0.5})
    write_test_image(paths.original_train("XX") / "base.png", size=32)
    original = write_test_image(paths.original_test("XX") / "sample.png", size=32)
    manifest = prepare_testing(config, paths, aligner=identity_aligner)
    expected = cv2.resize(original, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    split = cv2.imread(str(paths.prepared_test("XX") / "sample_00.png"))
    assert split is not None and np.array_equal(split, expected[5:13, 4:12])
    assert manifest.sources[0].splits[0].image == "sample_00.png"


def test_change_req_003_02(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path)
    write_test_image(paths.original_train("XX") / "base.png")
    write_test_image(paths.original_test("XX") / "sample.png")

    def fail(*_args: object) -> AlignedImage:
        raise AlignmentError("homography_failed")

    manifest = prepare_testing(config, paths, aligner=fail)
    assert manifest.sources[0].alignment.status == "undetermined"
    assert manifest.sources[0].splits == []


def test_change_req_003_03(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path, ranges=[{"id": 7, "x": 40, "y": 0}])
    write_test_image(paths.original_train("XX") / "base.png")
    write_test_image(paths.original_test("XX") / "sample.png")
    with pytest.raises(PreparationError, match="sample.png: range id 7"):
        prepare_testing(config, paths, aligner=identity_aligner)
    assert not paths.prepared_test("XX").exists()


def test_change_req_003_04(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path)
    write_test_image(paths.original_train("XX") / "base.png")
    (paths.original_test("XX") / "broken.png").parent.mkdir(parents=True)
    (paths.original_test("XX") / "broken.png").write_bytes(b"broken")
    target = paths.prepared_test("XX")
    target.mkdir(parents=True)
    (target / "keep").write_bytes(b"old")
    with pytest.raises(ImageReadError, match="broken.png"):
        prepare_testing(config, paths, aligner=identity_aligner)
    assert (target / "keep").read_bytes() == b"old"


@pytest.mark.parametrize("testing", [False, True])
def test_change_req_017_01(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], testing: bool
) -> None:
    config, paths = build_project(tmp_path)
    write_test_image(paths.original_train("XX") / "base.png")
    prepare = prepare_testing if testing else prepare_training
    source_dir = paths.original_test("XX") if testing else paths.original_train("XX")
    write_test_image(source_dir / "sample.png")
    with PreparationProgress() as progress:
        manifest = prepare(
            config, paths, aligner=identity_aligner, on_progress=progress.update
        )
    assert len(manifest.sources) == (1 if testing else 2)
    stderr = capsys.readouterr().err
    assert "準備進捗 0/" in stderr
    assert f"準備進捗 {len(manifest.sources)}/{len(manifest.sources)}" in stderr


@pytest.mark.parametrize("testing", [False, True])
def test_change_req_017_02(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], testing: bool
) -> None:
    config, paths = build_project(tmp_path)
    write_test_image(paths.original_train("XX") / "base.png")
    source_dir = paths.original_test("XX") if testing else paths.original_train("XX")
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "broken.png").write_bytes(b"broken")
    prepare = prepare_testing if testing else prepare_training
    with (
        pytest.raises(ImageReadError, match="broken.png"),
        PreparationProgress() as progress,
    ):
        prepare(config, paths, aligner=identity_aligner, on_progress=progress.update)
    stderr = capsys.readouterr().err
    assert "準備進捗 0/" in stderr
    assert "準備進捗 2/2" not in stderr
