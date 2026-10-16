from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import optuna
from conftest import build_project
from PIL import Image

from app.common.config import (
    SyntheticIntensityRange,
    SyntheticSizeRange,
    SyntheticValidationSettings,
)
from app.model_training.search import DatasetSplit, TrialOutcome, run_search
from app.model_training.synthetic_validation import (
    create_synthetic_validation,
    synthesize_image,
)


def test_req_030_s01(tmp_path: Path) -> None:
    config, _ = build_project(tmp_path)
    group = config.part.groups[0]
    group.optuna_settings.objective = "synthetic_auroc"
    image = tmp_path / "normal.png"
    Image.fromarray(np.full((32, 32, 3), 100, dtype=np.uint8)).save(image)
    original_hash = hashlib.sha256(image.read_bytes()).hexdigest()
    settings = SyntheticValidationSettings(
        seed=71,
        size_px=SyntheticSizeRange(min=4, max=12),
        intensity_range=SyntheticIntensityRange(min=0.05, max=0.5),
        images_per_validation_image=3,
    )
    first = create_synthetic_validation(
        (image,), tmp_path / "first", group=0, settings=settings
    )
    second = create_synthetic_validation(
        (image,), tmp_path / "second", group=0, settings=settings
    )
    assert len(first) == len(second) == 3
    assert [path.read_bytes() for path in first] == [
        path.read_bytes() for path in second
    ]
    assert hashlib.sha256(image.read_bytes()).hexdigest() == original_hash

    split = DatasetSplit(("a",), ("b",), (image,), (image,))

    def run() -> tuple[list[float], float, int]:
        study = optuna.create_study(
            direction="maximize", sampler=optuna.samplers.TPESampler(seed=42)
        )

        def runner(parameters, split, trial):
            del parameters, split
            return TrialOutcome([0.2], [0.1], image, [0.8 + trial.number * 0.01])

        study, _ = run_search(group, split, study, runner)
        return (
            [float(item.value) for item in study.trials if item.value is not None],
            float(study.best_value),
            study.best_trial.number,
        )

    group.optuna_settings.execution.trials = 2
    assert run() == run()


def test_req_030_s02(tmp_path: Path) -> None:
    image = tmp_path / "normal.png"
    pixels = np.full((48, 48, 3), 100, dtype=np.uint8)
    Image.fromarray(pixels).save(image)
    for defect in ("scratch", "stain", "spot", "foreign_patch"):
        small = synthesize_image(
            image,
            group=0,
            settings=SyntheticValidationSettings(types=[defect], intensity=0.1),
        )
        large = synthesize_image(
            image,
            group=0,
            settings=SyntheticValidationSettings(types=[defect], intensity=1.0),
        )
        assert np.any(np.asarray(small) != pixels)
        faint = synthesize_image(
            image,
            group=0,
            settings=SyntheticValidationSettings(types=[defect], intensity=0.001),
        )
        assert np.any(np.asarray(faint) != pixels)
        assert np.count_nonzero(np.asarray(large) != pixels) >= np.count_nonzero(
            np.asarray(small) != pixels
        )


def test_pixel_ranges_and_multiple_images(tmp_path: Path) -> None:
    image = tmp_path / "normal.png"
    pixels = np.full((48, 48, 3), 100, dtype=np.uint8)
    Image.fromarray(pixels).save(image)
    for defect in ("scratch", "stain", "spot", "foreign_patch"):
        settings = SyntheticValidationSettings(
            types=[defect],
            size_px=SyntheticSizeRange(min=8, max=8),
            intensity_range=SyntheticIntensityRange(min=0.2, max=0.2),
            images_per_validation_image=4,
        )
        generated = create_synthetic_validation(
            (image,), tmp_path / defect, group=0, settings=settings
        )
        assert len(generated) == 4
        for path in generated:
            changed = np.any(np.asarray(Image.open(path)) != pixels, axis=2)
            ys, xs = np.where(changed)
            assert len(xs) > 0
            assert int(np.ptp(xs)) + 1 <= 8
            assert int(np.ptp(ys)) + 1 <= 8
    assert np.array_equal(np.asarray(Image.open(image)), pixels)


def test_legacy_synthetic_bytes(tmp_path: Path) -> None:
    image = tmp_path / "normal.png"
    Image.fromarray(np.full((48, 48, 3), 100, dtype=np.uint8)).save(image)
    settings = SyntheticValidationSettings(
        types=["foreign_patch"], intensity=0.5, seed=42
    )
    generated = create_synthetic_validation(
        (image,), tmp_path / "legacy", group=0, settings=settings
    )
    assert generated[0].name == "000000_normal.png"
    assert hashlib.sha256(generated[0].read_bytes()).hexdigest() == (
        "8f0551609dcb2805f1457d25e7f99d333b3f84f00e26fbf82cb58e77004fbb58"
    )


def test_small_validation_images_generate_for_all_defects(tmp_path: Path) -> None:
    for size in (1, 2, 3):
        image = tmp_path / f"normal-{size}.png"
        pixels = np.full((size, size, 3), 100, dtype=np.uint8)
        Image.fromarray(pixels).save(image)
        for defect in ("scratch", "stain", "spot", "foreign_patch"):
            generated = synthesize_image(
                image,
                group=0,
                settings=SyntheticValidationSettings(types=[defect]),
            )
            assert generated.size == (size, size)
            assert np.any(np.asarray(generated) != pixels)
