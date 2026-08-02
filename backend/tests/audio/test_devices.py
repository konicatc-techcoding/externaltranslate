from __future__ import annotations

from typing import Any

import pytest

from backend.app.audio.devices import (
    AudioDeviceError,
    enumerate_input_devices,
    validate_input_selection,
)
from backend.app.audio.models import AudioSourceKind


class FakeAudioBackend:
    def __init__(self) -> None:
        self.checked: list[dict[str, Any]] = []

    def query_hostapis(self) -> list[dict[str, Any]]:
        return [
            {"name": "MME"},
            {"name": "Windows WASAPI"},
        ]

    def query_devices(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "Speakers",
                "hostapi": 1,
                "max_input_channels": 0,
                "max_output_channels": 2,
                "default_samplerate": 48000.0,
                "default_low_input_latency": 0.0,
            },
            {
                "name": "Test Interface Input",
                "hostapi": 1,
                "max_input_channels": 2,
                "max_output_channels": 0,
                "default_samplerate": 48000.0,
                "default_low_input_latency": 0.003,
            },
        ]

    def check_input_settings(self, **settings: Any) -> None:
        self.checked.append(settings)


def test_enumerate_input_devices_normalizes_real_capabilities() -> None:
    devices = enumerate_input_devices(FakeAudioBackend())

    assert len(devices) == 1
    device = devices[0]
    assert device.index == 1
    assert device.name == "Test Interface Input"
    assert device.host_api == "Windows WASAPI"
    assert device.max_input_channels == 2
    assert device.default_sample_rate == 48000
    assert device.source_kind is AudioSourceKind.INPUT_DEVICE


def test_validate_input_selection_checks_selected_channel_and_native_format() -> None:
    backend = FakeAudioBackend()
    device = enumerate_input_devices(backend)[0]

    selection = validate_input_selection(backend, device, channel=2)

    assert selection.channel == 2
    assert selection.stream_channels == 2
    assert selection.native_format.sample_rate == 48000
    assert selection.native_format.channels == 2
    assert backend.checked == [
        {
            "device": 1,
            "channels": 2,
            "dtype": "float32",
            "samplerate": 48000,
        }
    ]


@pytest.mark.parametrize("channel", [0, 3])
def test_validate_input_selection_rejects_invalid_channel(channel: int) -> None:
    backend = FakeAudioBackend()
    device = enumerate_input_devices(backend)[0]

    with pytest.raises(AudioDeviceError, match="輸入 channel"):
        validate_input_selection(backend, device, channel=channel)


def test_enumerate_input_devices_maps_backend_failure_to_traditional_chinese() -> None:
    class PortAudioLikeError(Exception):
        pass

    class BrokenBackend(FakeAudioBackend):
        def query_devices(self) -> list[dict[str, Any]]:
            raise PortAudioLikeError("driver unavailable")

    with pytest.raises(AudioDeviceError, match="無法列舉 Windows 音訊輸入裝置"):
        enumerate_input_devices(BrokenBackend())
