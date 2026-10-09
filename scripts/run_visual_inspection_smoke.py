#!/usr/bin/env python3
"""Run every visual-inspection CLI and persist a machine-readable smoke report."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import cv2
import torch

from app.common.config import load_config
from app.common.contracts import (
    BestTrialResult,
    InspectionResult,
    PreparationManifest,
    RunMetadata,
)
from app.common.paths import ProjectPaths
from app.common.result_index import read_current

COMMANDS = ["check", "train-pre", "train", "test-pre", "test"]


def run_command(
    root: Path, command: str, model: str, group: int | None = None
) -> dict[str, Any]:
    arguments = [command, "--model", model]
    if group is not None and command in {"train-pre", "train", "test"}:
        arguments.extend(["--group", str(group)])
    completed = subprocess.run(  # noqa: S603 - fixed allow-list supplied by main
        arguments,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    metadata = json.loads(lines[-1]) if lines else {}
    runtime_payload = dict(metadata)
    runtime_payload.pop("result", None)
    try:
        RunMetadata.model_validate(runtime_payload)
        metadata_valid = True
        metadata_error = None
    except Exception as error:  # report malformed CLI output without hiding other runs
        metadata_valid = False
        metadata_error = str(error)
    return {
        "command": command,
        "returncode": completed.returncode,
        "metadata": metadata,
        "metadata_valid": metadata_valid,
        "metadata_error": metadata_error,
        "stderr": completed.stderr,
    }


def _read_image(path: Path) -> None:
    if cv2.imread(str(path)) is None:
        raise ValueError(f"unreadable image: {path.name}")


def _read_manifest(path: Path) -> dict[str, int]:
    manifest = PreparationManifest.read_json(path)
    image_count = 0
    for source in manifest.sources:
        for split in source.splits:
            _read_image(path.parent / split.image)
            image_count += 1
    return {"sources": len(manifest.sources), "images": image_count}


def _read_checkpoint(path: Path) -> dict[str, str]:
    payload = torch.load(path, map_location="cpu", weights_only=False)
    metadata = payload.get("visual_inspection")
    if not isinstance(metadata, dict):
        raise ValueError("checkpoint visual_inspection metadata is missing")
    return {"model": str(metadata.get("model", ""))}


def _read_results(path: Path) -> dict[str, int]:
    json_paths = sorted(path.glob("*.json"))
    if not json_paths:
        raise ValueError("no inspection result JSON files")
    image_count = 0
    for json_path in json_paths:
        result = InspectionResult.read_json(json_path)
        for split in result.splits:
            if split.result_image is not None:
                _read_image(path / split.result_image)
                image_count += 1
    return {"results": len(json_paths), "images": image_count}


def inspect_artifacts(
    root: Path, model: str, group: int | None = None
) -> list[dict[str, Any]]:
    paths = ProjectPaths(root)
    config = load_config(root, model)
    groups = config.part.select_groups(group)
    checks: list[tuple[str, Path, Any]] = [
        ("check_image", paths.check_image(model), _read_image),
        ("test_manifest", paths.prepared_test(model) / "manifest.json", _read_manifest),
    ]
    for selected in config.part.select_groups():
        checks.append(
            (
                f"check_group_{selected.id}",
                paths.check_image(model, selected.id),
                _read_image,
            )
        )
    for selected in groups:
        checks.extend(
            [
                (
                    f"train_manifest_{selected.id}",
                    paths.prepared_train(model, selected.id) / "manifest.json",
                    _read_manifest,
                ),
                (
                    f"checkpoint_{selected.id}",
                    paths.checkpoint(model, selected.id),
                    _read_checkpoint,
                ),
                (
                    f"best_trial_{selected.id}",
                    paths.study_dir(model, selected.id) / "best_trial.json",
                    BestTrialResult.read_json,
                ),
            ]
        )
    current = read_current(
        paths, model, allowed_group_ids={item.id for item in config.part.groups}
    )
    for selected in groups:
        relative = current.get(selected.id)
        checks.append(
            (
                f"results_{selected.id}",
                paths.results(model) / relative
                if relative
                else paths.results(model) / "missing",
                _read_results,
            )
        )
    artifacts: list[dict[str, Any]] = []
    for name, path, reader in checks:
        record: dict[str, Any] = {
            "name": name,
            "path": str(path.relative_to(root)),
            "exists": path.exists(),
            "readable": False,
        }
        try:
            details = reader(path)
            record["readable"] = True
            if details is not None:
                record["details"] = (
                    details.model_dump(mode="json")
                    if hasattr(details, "model_dump")
                    else details
                )
        except Exception as error:
            record["error"] = str(error)
        artifacts.append(record)
    return artifacts


def nvidia_driver_versions() -> list[str]:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return []
    completed = subprocess.run(  # noqa: S603 - executable resolved with shutil.which
        [
            executable,
            "--query-gpu=driver_version",
            "--format=csv,noheader",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return []
    return sorted(
        {line.strip() for line in completed.stdout.splitlines() if line.strip()}
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--group", type=int)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    runs = [run_command(root, command, args.model, args.group) for command in COMMANDS]
    artifacts = inspect_artifacts(root, args.model, args.group)
    report = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "model": args.model,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "nvidia_driver_versions": nvidia_driver_versions(),
        "runs": runs,
        "artifacts": artifacts,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return (
        0
        if all(run["returncode"] == 0 and run["metadata_valid"] for run in runs)
        and all(artifact["readable"] for artifact in artifacts)
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
