from __future__ import annotations

from typing import Any

from backend.app.audio import capture
from backend.app.audio.models import CaptureStats, MeterReading


class FakeSource:
    @property
    def active(self) -> bool:
        return False

    @property
    def latest_meter(self) -> MeterReading:
        return MeterReading(0.0, 0.0, -120.0, -120.0, False)

    @property
    def stats(self) -> CaptureStats:
        return CaptureStats(0, 0, 0, 0, 0, 0, 0)

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def get_pcm_chunk(self, timeout: float) -> bytes:
        del timeout
        return b""


def audio_settings(**overrides: object) -> dict[str, Any]:
    audio: dict[str, object] = {
        "source_kind": "input_device",
        "device_index": 7,
        "loopback_endpoint_index": None,
        "channel": 2,
        "target_sample_rate": 16000,
        "chunk_duration_ms": 100,
        "raw_queue_capacity": 32,
        "pcm_queue_capacity": 50,
    }
    audio.update(overrides)
    return {"audio": audio}


def test_configured_audio_factory_wires_input_selection_and_queues() -> None:
    captured: dict[str, object] = {}
    expected_source = FakeSource()

    def create_input(**kwargs: object) -> tuple[FakeSource, object]:
        captured.update(kwargs)
        return expected_source, object()

    builder = getattr(capture, "create_audio_source_from_settings", None)
    assert builder is not None, "production audio settings factory is missing"

    source = builder(audio_settings(), input_source_creator=create_input)

    assert source is expected_source
    assert captured == {
        "device_index": 7,
        "channel": 2,
        "raw_queue_capacity": 32,
        "pcm_queue_capacity": 50,
    }


def test_configured_audio_factory_wires_loopback_selection_and_queues() -> None:
    captured: dict[str, object] = {}
    expected_source = FakeSource()

    def create_loopback(**kwargs: object) -> FakeSource:
        captured.update(kwargs)
        return expected_source

    source = capture.create_audio_source_from_settings(
        audio_settings(
            source_kind="wasapi_loopback",
            device_index=None,
            loopback_endpoint_index=11,
        ),
        loopback_source_creator=create_loopback,
    )

    assert source is expected_source
    assert captured == {
        "endpoint_index": 11,
        "raw_queue_capacity": 32,
        "pcm_queue_capacity": 50,
    }
