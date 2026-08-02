from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AudioSourceKind(StrEnum):
    """Supported source identities; Stage 1 implements input devices only."""

    INPUT_DEVICE = "input_device"
    WASAPI_LOOPBACK = "wasapi_loopback"


@dataclass(frozen=True, slots=True)
class AudioFormat:
    sample_rate: int
    channels: int
    dtype: str

    def __post_init__(self) -> None:
        if self.sample_rate <= 0:
            raise ValueError("sample_rate 必須大於 0。")
        if self.channels <= 0:
            raise ValueError("channels 必須大於 0。")


@dataclass(frozen=True, slots=True)
class AudioDeviceInfo:
    index: int
    name: str
    host_api: str
    max_input_channels: int
    default_sample_rate: int
    low_input_latency: float
    source_kind: AudioSourceKind = AudioSourceKind.INPUT_DEVICE


@dataclass(frozen=True, slots=True)
class InputSelection:
    device: AudioDeviceInfo
    channel: int | None
    stream_channels: int
    native_format: AudioFormat


@dataclass(frozen=True, slots=True)
class LoopbackEndpointInfo:
    index: int
    name: str
    host_api: str
    channels: int
    default_sample_rate: int
    low_input_latency: float
    is_default: bool
    source_kind: AudioSourceKind = AudioSourceKind.WASAPI_LOOPBACK


@dataclass(frozen=True, slots=True)
class LoopbackSelection:
    endpoint: LoopbackEndpointInfo
    native_format: AudioFormat


@dataclass(frozen=True, slots=True)
class MeterReading:
    rms: float
    peak: float
    rms_dbfs: float
    peak_dbfs: float
    clipping: bool


@dataclass(frozen=True, slots=True)
class CaptureStats:
    callback_blocks: int
    callback_errors: int
    status_events: int
    processing_errors: int
    raw_dropped: int
    pcm_chunks: int
    pcm_dropped: int
