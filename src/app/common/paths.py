"""Safe project path resolution for model-scoped artifacts."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

MODEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def validate_model_name(model: str) -> str:
    """Return a safe model name or raise an actionable error."""

    if not MODEL_PATTERN.fullmatch(model):
        raise ValueError(
            f"model must match ^[A-Za-z0-9][A-Za-z0-9_-]*$; received {model!r}"
        )
    return model


def ensure_within(root: Path, candidate: Path) -> Path:
    """Resolve a path and ensure it remains under ``root``."""

    resolved_root = root.resolve()
    resolved = candidate.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f"path escapes managed root: {candidate}")
    return resolved


def ensure_no_symlink_components(root: Path, candidate: Path) -> None:
    """Reject symlinks between a managed root and a prepared input path."""

    relative = candidate.relative_to(root)
    current = root
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            raise ValueError(f"prepared input must not be a symlink: {current}")


@dataclass(frozen=True)
class ProjectPaths:
    """All known filesystem locations for one project root."""

    root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", self.root.resolve())

    def model_config(self, model: str) -> Path:
        validate_model_name(model)
        return ensure_within(self.root, self.root / "config" / f"part_{model}.json")

    @property
    def global_config(self) -> Path:
        return ensure_within(self.root, self.root / "config" / "setting.ini")

    def original_train(self, model: str) -> Path:
        return self._model_dir("data/01_original_train", model)

    def original_test(self, model: str) -> Path:
        return self._model_dir("data/02_original_test", model)

    def base_image(self, model: str, filename: str) -> Path:
        return ensure_within(
            self.original_train(model), self.original_train(model) / filename
        )

    def check_image(self, model: str) -> Path:
        validate_model_name(model)
        return ensure_within(self.root, self.root / "data/03_check" / f"{model}.png")

    def prepared_train(self, model: str) -> Path:
        ensure_no_symlink_components(
            self.root, self.root / "data/04_train" / validate_model_name(model)
        )
        return self._model_dir("data/04_train", model)

    def prepared_test(self, model: str) -> Path:
        ensure_no_symlink_components(
            self.root, self.root / "data/05_test" / validate_model_name(model)
        )
        return self._model_dir("data/05_test", model)

    def results(self, model: str) -> Path:
        return self._model_dir("data/06_result", model)

    def study_dir(self, model: str) -> Path:
        return self._model_dir("optuna", model)

    def checkpoint(self, model: str) -> Path:
        validate_model_name(model)
        return ensure_within(self.root, self.root / "weights" / f"{model}.ckpt")

    @property
    def pretrained(self) -> Path:
        return ensure_within(self.root, self.root / "pretrained")

    def _model_dir(self, parent: str, model: str) -> Path:
        validate_model_name(model)
        return ensure_within(self.root, self.root / parent / model)

    def remove_model_artifact(self, path: Path, *, expected: Path) -> None:
        """Remove only an explicitly resolved model artifact."""

        target = ensure_within(self.root, path)
        safe_expected = ensure_within(self.root, expected)
        if target != safe_expected:
            raise ValueError(f"refusing to remove unexpected path: {target}")
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
