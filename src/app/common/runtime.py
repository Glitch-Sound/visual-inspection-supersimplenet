"""Runtime device selection and operation metadata."""

from __future__ import annotations

import importlib.metadata
import platform
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from app.common.contracts import DeviceMetadata, PlatformMetadata, RunMetadata


@dataclass(frozen=True)
class DeviceSelection:
    device: Literal["cuda", "cpu"]
    name: str
    reason: str


def select_device(
    cuda_available: Callable[[], bool] | None = None,
    cuda_name: Callable[[], str] | None = None,
) -> DeviceSelection:
    """Prefer CUDA and make every fallback reason explicit."""

    if cuda_available is None or cuda_name is None:
        try:
            import torch

            cuda_available = torch.cuda.is_available

            def current_cuda_name() -> str:
                return torch.cuda.get_device_name(0)

            cuda_name = current_cuda_name
        except (ImportError, RuntimeError) as error:
            return DeviceSelection("cpu", platform.processor() or "CPU", str(error))
    try:
        if cuda_available():
            return DeviceSelection("cuda", cuda_name(), "CUDA is available")
        return DeviceSelection(
            "cpu", platform.processor() or "CPU", "CUDA is unavailable"
        )
    except RuntimeError as error:
        return DeviceSelection(
            "cpu", platform.processor() or "CPU", f"CUDA initialization failed: {error}"
        )


def package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for package in (
        "anomalib",
        "torch",
        "torchvision",
        "opencv-python-headless",
        "optuna",
    ):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not-installed"
    return versions


@dataclass
class RunRecorder:
    command: str
    model: str
    device: DeviceSelection
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_monotonic: float = field(default_factory=time.monotonic)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    _finished: RunMetadata | None = field(default=None, init=False, repr=False)

    def finish(self, exit_code: int) -> RunMetadata:
        if self._finished is not None and (
            self._finished.exit_code == exit_code or exit_code == 0
        ):
            return self._finished
        ended_at = datetime.now(UTC)
        self._finished = RunMetadata(
            command=self.command,
            model=self.model,
            started_at=self.started_at,
            ended_at=ended_at,
            duration_seconds=max(0.0, time.monotonic() - self.started_monotonic),
            exit_code=exit_code,
            status="success" if exit_code == 0 else "error",
            device=DeviceMetadata(
                type=self.device.device,
                name=self.device.name,
                reason=self.device.reason,
            ),
            platform=PlatformMetadata(
                system=platform.system(),
                release=platform.release(),
                machine=platform.machine(),
                python=sys.version.split()[0],
            ),
            dependencies=package_versions(),
            warnings=list(self.warnings),
            errors=list(self.errors),
        )
        return self._finished
