"""Regression checks for capability package boundaries and command registration."""

from __future__ import annotations

import ast
import importlib.metadata
import subprocess
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parents[1] / "src" / "app"
CAPABILITIES = {"image_preparation", "model_training", "model_evaluation"}
ENTRY_POINTS = {
    "check": "app.image_preparation.cli:check_cli",
    "train-pre": "app.image_preparation.cli:train_pre_cli",
    "train": "app.model_training.cli:train_cli",
    "test-pre": "app.image_preparation.cli:test_pre_cli",
    "test": "app.model_evaluation.cli:test_cli",
}


def test_capability_import_boundaries() -> None:
    packages = CAPABILITIES | {"common"}
    assert {
        path.name
        for path in PACKAGE_ROOT.iterdir()
        if path.is_dir() and (path / "__init__.py").exists()
    } == packages
    for package in packages:
        for path in (PACKAGE_ROOT / package).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports = [
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            ]
            imports.extend(
                node.module or ""
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
            )
            for name in imports:
                parts = name.split(".")
                if len(parts) < 2 or parts[0] != "app":
                    continue
                target = parts[1]
                if package == "common":
                    assert target not in CAPABILITIES, path
                elif target in CAPABILITIES:
                    assert target == package, path


def test_console_script_entry_points() -> None:
    distribution = importlib.metadata.distribution("visual-inspection-supersimplenet")
    scripts = {
        item.name: item
        for item in distribution.entry_points
        if item.group == "console_scripts"
    }
    assert set(scripts) == set(ENTRY_POINTS)
    for name, target in ENTRY_POINTS.items():
        assert scripts[name].value == target
        assert callable(scripts[name].load())
        executable = Path(sys.executable).parent / name
        if sys.platform == "win32":
            executable = executable.with_suffix(".exe")
        completed = subprocess.run(  # noqa: S603 - installed environment script
            [str(executable), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert "--model" in completed.stdout
        assert ("--restart" in completed.stdout) == (name in {"train", "test"})
