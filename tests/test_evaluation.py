from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
import torch
from conftest import build_project, write_test_image

from app.common.artifact_transaction import _transaction_path
from app.common.config import load_config
from app.common.contracts import (
    AlignmentResult,
    BestTrialResult,
    InspectionResult,
    PreparationManifest,
    PreparedSource,
    PreparedSplit,
    RunMetadata,
    ScoreContract,
    TrialParametersContract,
)
from app.common.runtime import DeviceSelection, RunRecorder
from app.model_evaluation.evaluation import (
    effective_threshold,
    evaluate_model,
    evaluate_split,
    restart_evaluation,
    validate_best_trial_contract,
    validate_score_contract,
)
from app.model_evaluation.predictor import (
    CheckpointPredictor,
    Prediction,
    load_checkpoint_metadata,
)
from app.model_training.artifacts import _write_transaction_journal


def test_load_checkpoint_metadata_with_preprocessor(tmp_path: Path) -> None:
    from app.common.model_adapter import TunableSupersimplenet

    checkpoint = tmp_path / "model.ckpt"
    metadata = {
        "model": "XX",
        "score_source": "supersimplenet.pred_score",
        "anomalib_post_processor": False,
        "threshold": 0.5,
    }
    torch.save(
        {
            "state_dict": {},
            "pre_processor": TunableSupersimplenet.configure_pre_processor((256, 256)),
            "visual_inspection": metadata,
        },
        checkpoint,
    )

    assert load_checkpoint_metadata(checkpoint) == metadata


def test_evaluation_starts_with_preprocessor_checkpoint(tmp_path: Path) -> None:
    from app.common.model_adapter import TunableSupersimplenet

    config, paths = build_project(tmp_path)
    config = config.model_copy(
        update={
            "part": config.part.model_copy(
                update={
                    "optuna_settings": config.part.optuna_settings.model_copy(
                        update={
                            "threshold": config.part.optuna_settings.threshold.model_copy(
                                update={"value": 0.5}
                            )
                        }
                    )
                }
            )
        }
    )
    checkpoint = paths.checkpoint("XX")
    checkpoint.parent.mkdir(parents=True)
    torch.save(
        {
            "state_dict": {},
            "hyper_parameters": {
                "pre_processor": TunableSupersimplenet.configure_pre_processor(
                    (256, 256)
                )
            },
            "visual_inspection": {
                "model": "XX",
                "score_source": "supersimplenet.pred_score",
                "anomalib_post_processor": False,
                "threshold": 0.5,
            },
        },
        checkpoint,
    )
    prepared_dir = paths.prepared_test("XX")
    image_path = prepared_dir / "source_00.png"
    write_test_image(image_path)
    recorder = RunRecorder("test", "XX", DeviceSelection("cpu", "CPU", "test"))
    PreparationManifest(
        model="XX",
        created_at=recorder.started_at,
        sources=[
            PreparedSource(
                source_image="source.png",
                alignment=AlignmentResult(status="aligned"),
                splits=[
                    PreparedSplit(
                        source_image="source.png", split_id=0, image=image_path.name
                    )
                ],
            )
        ],
    ).write_json(prepared_dir / "manifest.json")
    predictions = 0

    def predictor(image: np.ndarray) -> Prediction:
        nonlocal predictions
        predictions += 1
        return Prediction(0.2, np.zeros(image.shape[:2], dtype=np.float32))

    results = evaluate_model(
        config,
        paths,
        predictor=predictor,
        finish_runtime=lambda: recorder.finish(0),
    )

    assert predictions == 1
    assert len(results) == 1
    assert results[0].overall_status == "normal"
    assert (paths.results("XX") / "source.png.json").is_file()


def test_load_checkpoint_metadata_rejects_missing_metadata(tmp_path: Path) -> None:
    checkpoint = tmp_path / "model.ckpt"
    torch.save({"state_dict": {}}, checkpoint)

    with pytest.raises(ValueError, match="lacks visual_inspection metadata"):
        load_checkpoint_metadata(checkpoint)


def test_test_cli_recovers_interrupted_training_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _config, paths = build_project(tmp_path)
    config_path = paths.model_config("XX")
    config_payload = json.loads(config_path.read_text(encoding="utf-8"))
    config_payload["optuna_settings"]["threshold"]["value"] = 0.5
    config_path.write_text(json.dumps(config_payload) + "\n", encoding="utf-8")

    checkpoint = paths.checkpoint("XX")
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"previous checkpoint")
    best_path = paths.study_dir("XX") / "best_trial.json"
    best_path.parent.mkdir(parents=True)
    BestTrialResult(
        model="XX",
        trial_number=0,
        parameters=TrialParametersContract(
            learning_rate_multiplier=1.0,
            batch_size=4,
            epochs=200,
            feature_layers=["layer2"],
            image_size=256,
        ),
        objective=0.1,
        checkpoint="weights/XX.ckpt",
        score_contract=ScoreContract(),
        threshold=0.5,
        train_sources=["train.png"],
        validation_sources=["validation.png"],
        seed=42,
        dependencies={},
    ).write_json(best_path)
    targets = {"checkpoint": checkpoint, "config": config_path, "best_trial": best_path}
    previous = {name: path.read_bytes() for name, path in targets.items()}
    for path in targets.values():
        shutil.copy2(path, _transaction_path(path, "backup"))
        path.write_bytes(b"interrupted replacement")
    journal = paths.study_dir("XX") / ".artifact-transaction.json"
    _write_transaction_journal(journal, dict.fromkeys(targets, True))

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "app.common.cli.select_device",
        lambda: DeviceSelection("cpu", "CPU", "test"),
    )

    def make_predictor(path: Path, **_kwargs: object) -> object:
        assert path == checkpoint
        assert {name: item.read_bytes() for name, item in targets.items()} == previous
        assert not journal.exists()
        return object()

    monkeypatch.setattr("app.model_evaluation.cli.CheckpointPredictor", make_predictor)
    monkeypatch.setattr("app.model_evaluation.cli.evaluate_model", lambda *_a, **_k: [])

    from app.model_evaluation.cli import _test_command

    _test_command("XX", restart=False)
    output = json.loads(capsys.readouterr().out)
    assert output["exit_code"] == 0
    assert output["result"] == "0 source images"
    assert {name: path.read_bytes() for name, path in targets.items()} == previous


def test_evaluation_records_normal_split(tmp_path: Path) -> None:
    image_path = tmp_path / "split.png"
    original = write_test_image(image_path)
    result_path = tmp_path / "result.png"
    result = evaluate_split(
        image_path=image_path,
        split_id=0,
        threshold=0.5,
        predictor=lambda image: Prediction(0.2, np.zeros(image.shape[:2], np.float32)),
        result_path=result_path,
    )
    assert result.status == "normal"
    assert result.score == 0.2
    written = cv2.imread(str(result_path))
    assert written is not None
    assert np.array_equal(written, original)


@pytest.mark.parametrize("score", [0.5, 0.8])
def test_evaluation_visualizes_anomalous_split(tmp_path: Path, score: float) -> None:
    image_path = tmp_path / "split.png"
    original = write_test_image(image_path)
    anomaly_map = np.linspace(
        0, 1, original.shape[0] * original.shape[1], dtype=np.float32
    )
    anomaly_map = anomaly_map.reshape(original.shape[:2])
    result_path = tmp_path / "result.png"
    result = evaluate_split(
        image_path=image_path,
        split_id=0,
        threshold=0.5,
        predictor=lambda _image: Prediction(score, anomaly_map),
        result_path=result_path,
    )
    assert result.status == "anomaly"
    written = cv2.imread(str(result_path))
    assert written is not None
    assert not np.array_equal(written, original)


@pytest.mark.parametrize(
    ("metadata_update", "message"),
    [
        ({"model": "YY"}, "model mismatch"),
        ({"score_source": "other.score"}, "score_source"),
        ({"anomalib_post_processor": True}, "anomalib_post_processor"),
        ({"threshold": 0.6}, "threshold"),
    ],
)
def test_evaluation_rejects_mismatched_checkpoint_contract(
    tmp_path: Path, metadata_update: dict[str, object], message: str
) -> None:
    config, _paths = build_project(tmp_path)
    config = config.model_copy(
        update={
            "part": config.part.model_copy(
                update={
                    "optuna_settings": config.part.optuna_settings.model_copy(
                        update={
                            "threshold": config.part.optuna_settings.threshold.model_copy(
                                update={"value": 0.5}
                            )
                        }
                    )
                }
            )
        }
    )
    metadata: dict[str, object] = {
        "model": "XX",
        "score_source": "supersimplenet.pred_score",
        "anomalib_post_processor": False,
        "threshold": 0.5,
    }
    metadata.update(metadata_update)

    with pytest.raises(ValueError, match=message):
        validate_score_contract(config, metadata)


def test_evaluation_rejects_invalid_best_trial_contract(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path)
    config = config.model_copy(
        update={
            "part": config.part.model_copy(
                update={
                    "optuna_settings": config.part.optuna_settings.model_copy(
                        update={
                            "threshold": config.part.optuna_settings.threshold.model_copy(
                                update={"value": 0.5}
                            )
                        }
                    )
                }
            )
        }
    )
    best = BestTrialResult(
        model="XX",
        trial_number=0,
        parameters=TrialParametersContract(
            learning_rate_multiplier=1.0,
            batch_size=4,
            epochs=200,
            feature_layers=["layer2"],
            image_size=256,
        ),
        objective=0.1,
        checkpoint="weights/XX.ckpt",
        score_contract=ScoreContract(),
        threshold=0.5,
        train_sources=["train.png"],
        validation_sources=["validation.png"],
        seed=42,
        dependencies={},
    )
    validate_best_trial_contract(config, paths, best)

    for update, message in (
        ({"model": "YY"}, "model mismatch"),
        ({"checkpoint": "weights/YY.ckpt"}, "checkpoint mismatch"),
        ({"threshold": 0.6}, "threshold"),
        (
            {"parameters": best.parameters.model_copy(update={"image_size": 999})},
            "image_size",
        ),
    ):
        with pytest.raises(ValueError, match=message):
            validate_best_trial_contract(config, paths, best.model_copy(update=update))

    with pytest.raises(ValueError, match="parameters"):
        BestTrialResult.model_validate(
            {
                **best.model_dump(mode="json"),
                "parameters": {"learning_rate_multiplier": "invalid"},
            }
        )


def test_evaluation_restart_replaces_only_results(tmp_path: Path) -> None:
    _config, paths = build_project(tmp_path)
    results = paths.results("XX")
    results.mkdir(parents=True)
    (results / "old.json").write_text("{}", encoding="utf-8")
    checkpoint = paths.checkpoint("XX")
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text("keep", encoding="utf-8")
    prepared = paths.prepared_test("XX")
    prepared.mkdir(parents=True)
    (prepared / "manifest.json").write_text("keep", encoding="utf-8")
    restart_evaluation(paths, "XX")
    assert not results.exists()
    assert checkpoint.read_text(encoding="utf-8") == "keep"
    assert (prepared / "manifest.json").read_text(encoding="utf-8") == "keep"


def _change_evaluation_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    override: float | None,
    present: bool = True,
    score: float = 0.3,
) -> InspectionResult:
    _config, paths = build_project(tmp_path)
    payload = json.loads(paths.model_config("XX").read_text(encoding="utf-8"))
    payload["optuna_settings"]["threshold"]["value"] = 0.5
    if present:
        payload["inspection_threshold"] = override
    else:
        payload.pop("inspection_threshold", None)
    paths.model_config("XX").write_text(json.dumps(payload), encoding="utf-8")
    config = load_config(tmp_path, "XX")
    prepared = paths.prepared_test("XX")
    write_test_image(prepared / "source_00.png")
    recorder = RunRecorder("test", "XX", DeviceSelection("cpu", "CPU", "test"))
    PreparationManifest(
        model="XX",
        created_at=recorder.started_at,
        sources=[
            PreparedSource(
                source_image="source.png",
                alignment=AlignmentResult(status="aligned"),
                splits=[
                    PreparedSplit(
                        source_image="source.png", split_id=0, image="source_00.png"
                    )
                ],
            )
        ],
    ).write_json(prepared / "manifest.json")
    monkeypatch.setattr(
        "app.model_evaluation.evaluation.load_checkpoint_metadata",
        lambda _path: {
            "model": "XX",
            "score_source": "supersimplenet.pred_score",
            "anomalib_post_processor": False,
            "threshold": 0.5,
        },
    )
    selected_thresholds: list[float] = []

    def predict(image: np.ndarray) -> Prediction:
        assert selected_thresholds == [0.5 if override is None else override]
        return Prediction(score, np.zeros(image.shape[:2], dtype=np.float32))

    result = evaluate_model(
        config,
        paths,
        predictor=predict,
        finish_runtime=lambda: recorder.finish(0),
        on_threshold_selected=selected_thresholds.append,
    )[0]
    assert selected_thresholds == [result.threshold]
    saved = InspectionResult.read_json(paths.results("XX") / "source.png.json")
    assert saved.threshold == result.threshold
    return result


def test_change_req_018_01(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _change_evaluation_case(
        tmp_path, monkeypatch, override=None, present=False
    )
    assert result.threshold == 0.5
    assert result.overall_status == "normal"


def test_change_req_018_02(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _change_evaluation_case(tmp_path, monkeypatch, override=None)
    assert result.threshold == 0.5


def test_change_req_018_03(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _change_evaluation_case(tmp_path, monkeypatch, override=0.2)
    assert result.threshold == 0.2
    assert result.overall_status == "anomaly"
    payload = json.loads((tmp_path / "config" / "part_XX.json").read_text())
    assert payload["optuna_settings"]["threshold"]["value"] == 0.5


@pytest.mark.parametrize("override,score", [(0.0, 0.0), (1.0, 1.0)])
def test_change_req_018_04(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, override: float, score: float
) -> None:
    result = _change_evaluation_case(
        tmp_path, monkeypatch, override=override, score=score
    )
    assert result.threshold == override
    assert result.overall_status == "anomaly"


@pytest.mark.parametrize("invalid", [-0.1, 1.1, True, "0.5", float("inf")])
def test_change_req_018_05(tmp_path: Path, invalid: object) -> None:
    _config, paths = build_project(tmp_path)
    payload = json.loads(paths.model_config("XX").read_text())
    payload["inspection_threshold"] = invalid
    paths.model_config("XX").write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="inspection_threshold"):
        load_config(tmp_path, "XX")
    assert not paths.results("XX").exists()


def test_change_req_018_06(tmp_path: Path) -> None:
    config, paths = build_project(tmp_path)
    config = config.model_copy(
        update={
            "part": config.part.model_copy(
                update={
                    "inspection_threshold": 0.2,
                    "optuna_settings": config.part.optuna_settings.model_copy(
                        update={
                            "threshold": config.part.optuna_settings.threshold.model_copy(
                                update={"value": 0.5}
                            )
                        }
                    ),
                }
            )
        }
    )
    assert effective_threshold(config, 0.5) == 0.2
    with pytest.raises(ValueError, match="threshold"):
        validate_score_contract(
            config,
            {
                "model": "XX",
                "score_source": "supersimplenet.pred_score",
                "anomalib_post_processor": False,
                "threshold": 0.6,
            },
        )
    assert not paths.results("XX").exists()


def test_predictor_uses_model_preprocessor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[torch.Tensor] = []

    class Preprocess:
        def __call__(self, tensor: torch.Tensor) -> torch.Tensor:
            calls.append(tensor.clone())
            return torch.nn.functional.interpolate(
                tensor, size=(7, 7), mode="bilinear", antialias=True
            )

    class Core:
        def __call__(self, tensor: torch.Tensor) -> SimpleNamespace:
            assert tuple(tensor.shape) == (1, 3, 7, 7)
            return SimpleNamespace(
                pred_score=torch.tensor([0.2]),
                anomaly_map=torch.zeros((1, 1, 7, 7)),
            )

    class Model:
        pre_processor = SimpleNamespace(transform=Preprocess())
        model = Core()

        def load_state_dict(self, _state: dict[str, object]) -> None:
            pass

        def to(self, _device: torch.device) -> None:
            pass

        def eval(self) -> None:
            pass

    monkeypatch.setattr(
        "app.model_evaluation.predictor.create_supersimplenet",
        lambda **_kwargs: Model(),
    )
    checkpoint = tmp_path / "model.ckpt"
    torch.save({"state_dict": {}}, checkpoint)
    predictor = CheckpointPredictor(
        checkpoint,
        layers=["layer2"],
        image_size=7,
        learning_rate_multiplier=1.0,
        device="cpu",
    )

    image = np.zeros((9, 13, 3), dtype=np.uint8)
    prediction = predictor(image)

    assert prediction.score == pytest.approx(0.2)
    assert len(calls) == 1
    assert tuple(calls[0].shape) == (1, 3, 9, 13)


def test_evaluation_keeps_same_stem_different_extensions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, paths = build_project(tmp_path)
    config = config.model_copy(
        update={
            "part": config.part.model_copy(
                update={
                    "optuna_settings": config.part.optuna_settings.model_copy(
                        update={
                            "threshold": config.part.optuna_settings.threshold.model_copy(
                                update={"value": 0.5}
                            )
                        }
                    )
                }
            )
        }
    )
    prepared = paths.prepared_test("XX")
    sources: list[PreparedSource] = []
    for suffix in ("png", "jpg"):
        split_name = f"sample_00.{suffix}"
        write_test_image(prepared / split_name)
        sources.append(
            PreparedSource(
                source_image=f"sample.{suffix}",
                alignment=AlignmentResult(status="aligned"),
                splits=[
                    PreparedSplit(
                        source_image=f"sample.{suffix}",
                        split_id=0,
                        image=split_name,
                    )
                ],
            )
        )
    PreparationManifest(
        model="XX",
        created_at=RunRecorder(
            "test", "XX", DeviceSelection("cpu", "CPU", "test")
        ).started_at,
        sources=sources,
    ).write_json(prepared / "manifest.json")
    monkeypatch.setattr(
        "app.model_evaluation.evaluation.load_checkpoint_metadata",
        lambda _path: {
            "model": "XX",
            "score_source": "supersimplenet.pred_score",
            "anomalib_post_processor": False,
            "threshold": 0.5,
        },
    )
    recorder = RunRecorder("test", "XX", DeviceSelection("cpu", "CPU", "test"))

    evaluate_model(
        config,
        paths,
        predictor=lambda image: Prediction(
            0.2, np.zeros(image.shape[:2], dtype=np.float32)
        ),
        finish_runtime=lambda: recorder.finish(0),
    )

    result_names = {path.name for path in paths.results("XX").iterdir()}
    assert result_names == {
        "sample.png.json",
        "sample.jpg.json",
        "sample_00.png_result.png",
        "sample_00.jpg_result.png",
    }


def test_evaluation_persists_final_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, paths = build_project(tmp_path)
    config = config.model_copy(
        update={
            "part": config.part.model_copy(
                update={
                    "optuna_settings": config.part.optuna_settings.model_copy(
                        update={
                            "threshold": config.part.optuna_settings.threshold.model_copy(
                                update={"value": 0.5}
                            )
                        }
                    )
                }
            )
        }
    )
    prepared = paths.prepared_test("XX")
    image_path = prepared / "source_00.png"
    write_test_image(image_path)
    PreparationManifest(
        model="XX",
        created_at=RunRecorder(
            "test", "XX", DeviceSelection("cpu", "CPU", "test")
        ).started_at,
        sources=[
            PreparedSource(
                source_image="source.png",
                alignment=AlignmentResult(
                    status="undetermined", reason="homography_failed"
                ),
                splits=[
                    PreparedSplit(
                        source_image="source.png",
                        split_id=0,
                        image=image_path.name,
                    )
                ],
            )
        ],
    ).write_json(prepared / "manifest.json")
    monkeypatch.setattr(
        "app.model_evaluation.evaluation.load_checkpoint_metadata",
        lambda _path: {
            "model": "XX",
            "score_source": "supersimplenet.pred_score",
            "anomalib_post_processor": False,
            "threshold": 0.5,
        },
    )
    recorder = RunRecorder(
        "test", "XX", DeviceSelection("cpu", "CPU", "CUDA is unavailable")
    )
    prediction_completed = False

    def predictor(image: np.ndarray) -> Prediction:
        nonlocal prediction_completed
        prediction_completed = True
        raise RuntimeError("prediction failed")

    def finish_runtime() -> RunMetadata:
        assert prediction_completed
        return recorder.finish(0)

    results = evaluate_model(
        config,
        paths,
        predictor=predictor,
        finish_runtime=finish_runtime,
        record_warning=recorder.warnings.append,
        record_error=recorder.errors.append,
    )
    final_runtime = recorder.finish(0)
    restored = InspectionResult.read_json(paths.results("XX") / "source.png.json")

    assert results[0].runtime == final_runtime
    assert restored.runtime == final_runtime
    assert restored.runtime.duration_seconds >= 0
    assert restored.runtime.warnings == ["source.png: homography_failed"]
    assert restored.runtime.errors == ["source.png: split 0: prediction failed"]
