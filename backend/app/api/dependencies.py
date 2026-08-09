from __future__ import annotations

from collections.abc import Callable

from backend.app.audio.models import AudioDeviceInfo, LoopbackEndpointInfo
from backend.app.prerequisites.models import PrerequisiteResult
from backend.app.services.runtime import PipelineRuntime

PrerequisiteReporter = Callable[[], list[PrerequisiteResult]]
DeviceLister = Callable[[], list[AudioDeviceInfo]]
LoopbackLister = Callable[[], list[LoopbackEndpointInfo]]


def get_runtime() -> PipelineRuntime:  # pragma: no cover - replaced by the factory
    """Placeholder dependency; `create_app` overrides it with the real runtime."""
    raise RuntimeError("runtime 尚未初始化。")


def get_prerequisite_reporter() -> PrerequisiteReporter:  # pragma: no cover
    raise RuntimeError("prerequisite reporter 尚未初始化。")


def get_device_lister() -> DeviceLister:  # pragma: no cover
    raise RuntimeError("device lister 尚未初始化。")


def get_loopback_lister() -> LoopbackLister:  # pragma: no cover
    raise RuntimeError("loopback lister 尚未初始化。")
