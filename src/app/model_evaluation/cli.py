"""Model evaluation command entry point."""

from __future__ import annotations

import shutil
import sys
from typing import Any
from uuid import uuid4

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn

from app.common.cli import ExitCode, _run, show_stage
from app.common.config import load_config, preparation_fingerprint
from app.common.contracts import BestTrialResult, load_preparation_manifest
from app.common.paths import ProjectPaths
from app.common.result_index import (
    cleanup_generations,
    create_result_stage,
    publish_current,
    read_current,
)
from app.common.runtime import RunRecorder
from app.model_evaluation.evaluation import (
    evaluate_model,
    require_heatmap_range,
    validate_best_trial_contract,
    validate_score_contract,
)
from app.model_evaluation.predictor import CheckpointPredictor, load_checkpoint_metadata


class EvaluationProgress:
    """Render one source-image counter for evaluation on stderr."""

    def __init__(self) -> None:
        self._progress: Progress | None = None
        self._task_id: Any = None

    def __enter__(self) -> EvaluationProgress:
        if sys.stderr.isatty():
            self._progress = Progress(
                TextColumn("検査進捗"),
                BarColumn(),
                TextColumn("{task.completed}/{task.total}"),
                console=Console(stderr=True),
            )
            self._progress.start()
        return self

    def __exit__(self, *_args: object) -> None:
        if self._progress is not None:
            self._progress.stop()

    def update(self, processed: int, total: int) -> None:
        if self._progress is None:
            show_stage(f"検査進捗 {processed}/{total}")
            return
        if self._task_id is None:
            self._task_id = self._progress.add_task("検査進捗", total=total)
        self._progress.update(self._task_id, completed=processed, total=total)


def _test_command(
    model: str = typer.Option(..., "--model", help="処理対象の型番"),
    group: int | None = typer.Option(None, "--group", help="処理対象のグループID"),
) -> None:
    """型番別・グループ別モデルで試験画像を検査する。"""

    def action(paths: ProjectPaths, recorder: RunRecorder) -> str:
        show_stage("設定読込と全対象グループの学習成果物照合")
        config = load_config(paths.root, model)
        groups = config.part.select_groups(group)
        recorder.groups = [item.id for item in groups]
        manifest = load_preparation_manifest(
            paths.prepared_test(model),
            model=config.model,
            allowed_split_ids={item.id for item in config.part.ranges},
            fingerprint=preparation_fingerprint(config),
        )
        if group is not None:
            current = read_current(
                paths, model, allowed_group_ids={item.id for item in config.part.groups}
            )
        else:
            try:
                current = read_current(
                    paths,
                    model,
                    allowed_group_ids={item.id for item in config.part.groups},
                )
            except ValueError:
                current = {}
        stage = create_result_stage(paths, model)
        all_results = []
        try:
            with EvaluationProgress() as progress:
                progress.update(0, len(manifest.sources))
                for selected in groups:
                    try:
                        require_heatmap_range(selected)
                        best = BestTrialResult.read_json(
                            paths.study_dir(model, selected.id) / "best_trial.json"
                        )
                        validate_best_trial_contract(config, selected, paths, best)
                        metadata = load_checkpoint_metadata(
                            paths.checkpoint(model, selected.id)
                        )
                        validate_score_contract(config, selected, metadata)
                        params = best.parameters
                        predictor = CheckpointPredictor(
                            paths.checkpoint(model, selected.id),
                            layers=list(params.feature_layers),
                            image_size=params.image_size,
                            learning_rate_multiplier=params.learning_rate_multiplier,
                            device=recorder.device.device,
                        )
                        source = (
                            "暫定閾値"
                            if selected.inspection_threshold is None
                            else "検査用設定"
                        )

                        def show_threshold(
                            threshold: float,
                            *,
                            group_id: int = selected.id,
                            threshold_source: str = source,
                        ) -> None:
                            show_stage(
                                f"グループ {group_id} 判定閾値: {threshold} ({threshold_source})"
                            )

                        def show_progress(processed: int, total: int) -> None:
                            if 0 < processed < total:
                                progress.update(processed, total)

                        results = evaluate_model(
                            config,
                            selected,
                            paths,
                            predictor=predictor,
                            output_dir=stage / paths.group_name(selected.id),
                            finish_runtime=lambda: recorder.snapshot(ExitCode.SUCCESS),
                            record_warning=recorder.warnings.append,
                            record_error=recorder.errors.append,
                            on_threshold_selected=show_threshold,
                            on_progress=show_progress
                            if selected is groups[-1]
                            else None,
                            checkpoint_metadata=metadata,
                        )
                        all_results.extend(results)
                        for result in results:
                            result.runtime = recorder.snapshot(ExitCode.SUCCESS)
                            result.write_json(
                                stage
                                / paths.group_name(selected.id)
                                / f"{result.source_image}.json"
                            )
                        paths.result_generations(model).mkdir(
                            parents=True, exist_ok=True
                        )
                        generation = paths.result_generations(model) / uuid4().hex
                        generation.mkdir(parents=True, exist_ok=False)
                        old = current.get(selected.id)
                        if old is not None:
                            shutil.rmtree(paths.results(model) / old)
                        (stage / paths.group_name(selected.id)).replace(
                            generation / paths.group_name(selected.id)
                        )
                        current[selected.id] = (
                            f"generations/{generation.name}/{paths.group_name(selected.id)}"
                        )
                        publish_current(paths, model, current)
                    except (ValueError, FileNotFoundError) as error:
                        raise ValueError(
                            f"group {selected.id} failed: {error}; "
                            "rerun train or test-pre if artifacts are missing or inconsistent"
                        ) from error
                    except Exception as error:
                        raise RuntimeError(
                            f"group {selected.id} failed: {error}"
                        ) from error
                if manifest.sources:
                    progress.update(len(manifest.sources), len(manifest.sources))
        finally:
            if stage.exists():
                shutil.rmtree(stage)
        try:
            cleanup_generations(paths, model, current)
        except (OSError, ValueError) as error:
            recorder.warnings.append(f"result cleanup deferred: {error}")
        counts = {
            status: sum(result.overall_status == status for result in all_results)
            for status in ("normal", "anomaly", "undetermined")
        }
        show_stage(
            f"検査完了: 正常={counts['normal']} 異常={counts['anomaly']} "
            f"未判定={counts['undetermined']} 現行参照={paths.result_current(model)}"
        )
        return f"{len(all_results)} group-source results"

    _run("test", model, action, needs_device=True)


def test_cli() -> None:
    typer.run(_test_command)
