"""Image preparation command entry points."""

from __future__ import annotations

from pathlib import Path

import typer

from app.common.cli import PreparationProgress, _run, show_stage
from app.common.config import load_config
from app.common.paths import ProjectPaths
from app.common.runtime import RunRecorder
from app.image_preparation.preparation import (
    alignment_warning,
    create_check_image,
    prepare_testing,
    prepare_training,
)


def _check_command(
    model: str = typer.Option(..., "--model", help="処理対象の型番"),
) -> None:
    """分割位置を確認する。"""

    def action(paths: ProjectPaths, _recorder: RunRecorder) -> Path:
        show_stage("設定読込と基準画像・分割範囲の確認")
        config = load_config(paths.root, model)
        output = create_check_image(config, paths)
        show_stage(f"確認画像保存: 範囲数={len(config.part.ranges)} 保存先={output}")
        return output

    _run("check", model, action)


def _train_pre_command(
    model: str = typer.Option(..., "--model", help="処理対象の型番"),
) -> None:
    """学習画像を位置合わせして分割する。"""

    def action(paths: ProjectPaths, recorder: RunRecorder) -> str:
        show_stage("設定読込と学習元画像の列挙・位置合わせ・切り出し")
        config = load_config(paths.root, model)
        with PreparationProgress() as progress:
            manifest = prepare_training(config, paths, on_progress=progress.update)
        recorder.warnings.extend(
            alignment_warning(
                str(item["source_image"]), str(item["reason"]), testing=False
            )
            for item in manifest.excluded
            if item.get("reason") != "blacklist"
        )
        prepared = sum(bool(source.splits) for source in manifest.sources)
        excluded = sum(not source.splits for source in manifest.sources)
        blacklisted_splits = sum(
            item.get("reason") == "blacklist" for item in manifest.excluded
        )
        target = paths.prepared_train(model)
        show_stage(
            f"学習準備完了: 対象={len(manifest.sources)} 準備={prepared} "
            f"除外元画像={excluded} ブラックリスト除外分割={blacklisted_splits} "
            f"保存先={target}"
        )
        return str(target)

    _run("train-pre", model, action)


def _test_pre_command(
    model: str = typer.Option(..., "--model", help="処理対象の型番"),
) -> None:
    """試験画像を位置合わせして分割する。"""

    def action(paths: ProjectPaths, recorder: RunRecorder) -> str:
        show_stage("設定読込と試験元画像の列挙・位置合わせ・切り出し")
        config = load_config(paths.root, model)
        with PreparationProgress() as progress:
            manifest = prepare_testing(config, paths, on_progress=progress.update)
        recorder.warnings.extend(
            alignment_warning(
                source.source_image,
                source.alignment.reason or "alignment_failed",
                testing=True,
            )
            for source in manifest.sources
            if source.alignment.status != "aligned"
        )
        prepared = sum(bool(source.splits) for source in manifest.sources)
        undetermined = sum(
            source.alignment.status != "aligned" for source in manifest.sources
        )
        target = paths.prepared_test(model)
        show_stage(
            f"試験準備完了: 対象={len(manifest.sources)} 準備={prepared} "
            f"未判定={undetermined} 保存先={target}"
        )
        return str(target)

    _run("test-pre", model, action)


def check_cli() -> None:
    typer.run(_check_command)


def train_pre_cli() -> None:
    typer.run(_train_pre_command)


def test_pre_cli() -> None:
    typer.run(_test_pre_command)
