from __future__ import annotations

from typing import Protocol

from backend.app.audio.models import CaptureStats, MeterReading


class AudioSource(Protocol):
    @property
    def active(self) -> bool: ...

    @property
    def latest_meter(self) -> MeterReading: ...

    @property
    def stats(self) -> CaptureStats: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def get_pcm_chunk(self, timeout: float) -> bytes: ...
