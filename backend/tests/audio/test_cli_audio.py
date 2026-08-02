from __future__ import annotations

import wave
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from backend.app.audio.models import CaptureStats, MeterReading
from backend.app.audio.sources.input_device import AudioCaptureError
from backend.app.cli.audio_devices import build_audio_device_report
from backend.app.cli.audio_smoke import run_smoke_capture
from backend.app.cli.loopback_devices import build_loopback_endpoint_report


class FakeLoopbackBackend:
    def list_loopback_devices(self) -> list[dict[str, Any]]:
        return [
            {
                "index": 16,
                "name": "Test Speakers [Loopback]",
                "hostApi": 2,
                "maxInputChannels": 2,
                "defaultSampleRate": 48000.0,
                "defaultLowInputLatency": 0.003,
                "isLoopbackDevice": True,
            }
        ]

    def get_default_loopback_device(self) -> dict[str, Any]:
        return self.list_loopback_devices()[0]

    def check_loopback_format(self, *, device: int, channels: int, rate: int) -> None:
        del device, channels, rate


class FakeDeviceBackend:
    def query_hostapis(self) -> list[dict[str, Any]]:
        return [{"name": "Windows WASAPI"}]

    def query_devices(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "Test Interface Input",
                "hostapi": 0,
                "max_input_channels": 2,
                "max_output_channels": 0,
                "default_samplerate": 48000.0,
                "default_low_input_latency": 0.003,
            }
        ]

    def check_input_settings(self, **settings: Any) -> None:
        del settings


class FakeSource:
    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0
        self._run_chunks = [
            [b"\x00\x01" * 1600],
            [b"\x00\x01" * 1600],
        ]
        self._chunks: Iterator[bytes] = iter(())

    @property
    def active(self) -> bool:
        return self.start_calls > self.stop_calls

    @property
    def latest_meter(self) -> MeterReading:
        return MeterReading(0.25, 0.5, -12.0412, -6.0206, False)

    @property
    def stats(self) -> CaptureStats:
        return CaptureStats(1, 0, 0, 0, 0, 1, 0)

    def start(self) -> None:
        run_index = self.start_calls
        self.start_calls += 1
        chunks = self._run_chunks[run_index] if run_index < len(self._run_chunks) else []
        self._chunks = iter(chunks)

    def stop(self) -> None:
        self.stop_calls += 1

    def get_pcm_chunk(self, timeout: float) -> bytes:
        del timeout
        try:
            return next(self._chunks)
        except StopIteration as exc:
            raise TimeoutError("empty") from exc


def test_audio_device_report_contains_host_api_channel_and_native_rate() -> None:
    report = build_audio_device_report(FakeDeviceBackend())

    assert report["input_device_count"] == 1
    assert report["devices"][0] == {
        "index": 0,
        "name": "Test Interface Input",
        "host_api": "Windows WASAPI",
        "max_input_channels": 2,
        "default_sample_rate": 48000,
        "low_input_latency_ms": 3.0,
        "source_kind": "input_device",
    }


def test_loopback_report_identifies_render_endpoint_and_default() -> None:
    report = build_loopback_endpoint_report(FakeLoopbackBackend())

    assert report == {
        "loopback_endpoint_count": 1,
        "endpoints": [
            {
                "index": 16,
                "name": "Test Speakers",
                "host_api": "Windows WASAPI",
                "channels": 2,
                "default_sample_rate": 48000,
                "low_input_latency_ms": 3.0,
                "is_default": True,
                "source_kind": "wasapi_loopback",
            }
        ],
    }


def test_run_smoke_capture_writes_valid_pcm16_wave_and_verifies_restart(
    tmp_path: Path,
) -> None:
    source = FakeSource()
    output_path = tmp_path / "smoke.wav"
    times = iter([0.0, 0.0, 2.0])

    report = run_smoke_capture(
        source,
        duration_seconds=1.0,
        output_path=output_path,
        monotonic=lambda: next(times),
    )

    with wave.open(str(output_path), "rb") as recording:
        assert recording.getnchannels() == 1
        assert recording.getsampwidth() == 2
        assert recording.getframerate() == 16000
        assert recording.getnframes() == 1600

    assert report["pcm_chunks"] == 1
    assert report["pcm_bytes"] == 3200
    assert report["restart_verified"] is True
    assert report["meter"]["peak"] == 0.5
    assert source.start_calls == 2
    assert source.stop_calls == 2


def test_run_smoke_capture_fails_closed_when_no_pcm_is_received(
    tmp_path: Path,
) -> None:
    source = FakeSource()
    source._run_chunks[0] = []
    times = iter([0.0, 2.0])

    with pytest.raises(AudioCaptureError, match="未收到任何 PCM"):
        run_smoke_capture(
            source,
            duration_seconds=1.0,
            output_path=tmp_path / "empty.wav",
            monotonic=lambda: next(times),
        )

    assert source.start_calls == 1
    assert source.stop_calls == 1


def test_run_smoke_capture_keeps_default_recording_in_memory() -> None:
    source = FakeSource()
    times = iter([0.0, 0.0, 2.0])

    report = run_smoke_capture(
        source,
        duration_seconds=1.0,
        output_path=None,
        monotonic=lambda: next(times),
    )

    assert report["wave"]["frames"] == 1600
    assert report["recording_persisted"] is False


def test_run_smoke_capture_rejects_restart_without_pcm(tmp_path: Path) -> None:
    source = FakeSource()
    source._run_chunks[1] = []
    times = iter([0.0, 0.0, 2.0])

    with pytest.raises(AudioCaptureError, match="重新啟動.*PCM"):
        run_smoke_capture(
            source,
            duration_seconds=1.0,
            output_path=tmp_path / "restart-empty.wav",
            monotonic=lambda: next(times),
        )

    assert source.start_calls == 2
    assert source.stop_calls == 2
