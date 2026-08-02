from __future__ import annotations

import importlib
from collections.abc import Mapping, Sequence
from typing import Any, Protocol, cast

from backend.app.audio.models import AudioDeviceInfo, AudioFormat, InputSelection


class AudioDeviceError(RuntimeError):
    """Raised when device discovery or selection cannot be completed safely."""


class AudioDeviceBackend(Protocol):
    def query_hostapis(self) -> Sequence[Mapping[str, Any]]: ...

    def query_devices(self) -> Sequence[Mapping[str, Any]]: ...

    def check_input_settings(self, **settings: Any) -> None: ...


class SoundDeviceBackend:
    """Small adapter around sounddevice so discovery remains deterministic in tests."""

    def __init__(self) -> None:
        self._sounddevice: Any = importlib.import_module("sounddevice")

    def query_hostapis(self) -> Sequence[Mapping[str, Any]]:
        return cast(Sequence[Mapping[str, Any]], self._sounddevice.query_hostapis())

    def query_devices(self) -> Sequence[Mapping[str, Any]]:
        return cast(Sequence[Mapping[str, Any]], self._sounddevice.query_devices())

    def check_input_settings(self, **settings: Any) -> None:
        self._sounddevice.check_input_settings(**settings)


def enumerate_input_devices(backend: AudioDeviceBackend) -> list[AudioDeviceInfo]:
    try:
        host_apis = backend.query_hostapis()
        devices = backend.query_devices()
        normalized: list[AudioDeviceInfo] = []
        for index, device in enumerate(devices):
            max_input_channels = int(device["max_input_channels"])
            if max_input_channels <= 0:
                continue
            host_api_index = int(device["hostapi"])
            normalized.append(
                AudioDeviceInfo(
                    index=index,
                    name=str(device["name"]),
                    host_api=str(host_apis[host_api_index]["name"]),
                    max_input_channels=max_input_channels,
                    default_sample_rate=int(round(float(device["default_samplerate"]))),
                    low_input_latency=float(device["default_low_input_latency"]),
                )
            )
        return normalized
    except Exception as exc:
        raise AudioDeviceError(
            "無法列舉 Windows 音訊輸入裝置；請確認裝置已連接、驅動正常後再試。"
        ) from exc


def validate_input_selection(
    backend: AudioDeviceBackend,
    device: AudioDeviceInfo,
    *,
    channel: int,
) -> InputSelection:
    if channel < 1 or channel > device.max_input_channels:
        raise AudioDeviceError(
            f"輸入 channel {channel} 無效；{device.name} 可用範圍為 "
            f"1–{device.max_input_channels}。"
        )

    stream_channels = channel
    native_format = AudioFormat(
        sample_rate=device.default_sample_rate,
        channels=stream_channels,
        dtype="float32",
    )
    try:
        backend.check_input_settings(
            device=device.index,
            channels=stream_channels,
            dtype=native_format.dtype,
            samplerate=native_format.sample_rate,
        )
    except Exception as exc:
        raise AudioDeviceError(
            f"無法開啟 {device.name} 的輸入 channel {channel}，"
            "請確認 sample rate、channel 與 Windows 驅動設定。"
        ) from exc

    return InputSelection(
        device=device,
        channel=channel,
        stream_channels=stream_channels,
        native_format=native_format,
    )
