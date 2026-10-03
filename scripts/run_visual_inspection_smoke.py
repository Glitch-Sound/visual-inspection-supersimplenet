#!/usr/bin/env python3
"""Run every visual-inspection CLI and persist a machine-readable smoke report."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def run_command(root: Path, command: str, model: str) -> dict[str, Any]:
    completed = subprocess.run(  # noqa: S603 - fixed allow-list supplied by main
        [command, "--model", model],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    metadata = json.loads(lines[-1]) if lines else {}
    return {
        "command": command,
        "returncode": completed.returncode,
        "metadata": metadata,
        "stderr": completed.stderr,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    commands = ["check", "train-pre", "test-pre", "train", "test"]
    runs = [run_command(root, command, args.model) for command in commands]
    expected = [
        root / "data" / "03_check" / f"{args.model}.png",
        root / "data" / "04_train" / args.model / "manifest.json",
        root / "data" / "05_test" / args.model / "manifest.json",
        root / "weights" / f"{args.model}.ckpt",
        root / "optuna" / args.model / "best_trial.json",
        root / "data" / "06_result" / args.model,
    ]
    report = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "model": args.model,
        "runs": runs,
        "artifacts": [
            {"path": str(path.relative_to(root)), "exists": path.exists()}
            for path in expected
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return (
        0
        if all(run["returncode"] == 0 for run in runs)
        and all(artifact["exists"] for artifact in report["artifacts"])
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
