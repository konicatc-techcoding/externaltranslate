from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from typing import Any

from backend.app.audio.devices import (
    AudioDeviceBackend,
    AudioDeviceError,
    SoundDeviceBackend,
    enumerate_input_devices,
    validate_input_selection,
)
from backend.app.audio.models import InputSelection
from backend.app.audio.sources.base import AudioSource
from backend.app.audio.sources.input_device import (
    InputDeviceSource,
    InputStreamFactory,
)


def create_input_device_source(
    *,
    device_index: int,
    channel: int,
    device_backend: AudioDeviceBackend | None = None,
    stream_factory: InputStreamFactory | None = None,
    raw_queue_capacity: int = 32,
    pcm_queue_capacity: int = 50,
) -> tuple[InputDeviceSource, InputSelection]:
    backend = device_backend or SoundDeviceBackend()
    devices = enumerate_input_devices(backend)
    device = next((item for item in devices if item.index == device_index), None)
    if device is None:
        raise AudioDeviceError(
            f"找不到輸入裝置 index {device_index}；請重新執行裝置列舉後再選擇。"
        )
    selection = validate_input_selection(backend, device, channel=channel)
    return (
        InputDeviceSource(
            selection,
            stream_factory=stream_factory,
            raw_queue_capacity=raw_queue_capacity,
            pcm_queue_capacity=pcm_queue_capacity,
        ),
        selection,
    )


InputSourceCreator = Callable[..., tuple[AudioSource, object]]
LoopbackSourceCreator = Callable[..., AudioSource]


def create_audio_source_from_settings(
    settings: Mapping[str, Any],
    *,
    input_source_creator: InputSourceCreator | None = None,
    loopback_source_creator: LoopbackSourceCreator | None = None,
) -> AudioSource:
    """Build the configured v0.1 audio source from validated settings."""

    audio = settings.get("audio")
    if not isinstance(audio, Mapping):
        raise AudioDeviceError("缺少已驗證的 audio 設定。")
    source_kind = audio.get("source_kind")
    raw_queue_capacity = int(audio["raw_queue_capacity"])
    pcm_queue_capacity = int(audio["pcm_queue_capacity"])
    if source_kind == "input_device":
        device_index = audio.get("device_index")
        if not isinstance(device_index, int) or isinstance(device_index, bool):
            raise AudioDeviceError("尚未選擇 audio.device_index，無法啟動輸入裝置。")
        creator = input_source_creator or create_input_device_source
        source, _selection = creator(
            device_index=device_index,
            channel=int(audio["channel"]),
            raw_queue_capacity=raw_queue_capacity,
            pcm_queue_capacity=pcm_queue_capacity,
        )
        return source
    if source_kind == "wasapi_loopback":
        if loopback_source_creator is None:
            from backend.app.audio.sources.wasapi_loopback import WasapiLoopbackSource

            loopback_source_creator = WasapiLoopbackSource
        return loopback_source_creator(
            endpoint_index=audio.get("loopback_endpoint_index"),
            raw_queue_capacity=raw_queue_capacity,
            pcm_queue_capacity=pcm_queue_capacity,
        )
    raise AudioDeviceError(f"目前無法建構音訊來源：{source_kind}。")


class AudioSourceSwitchError(RuntimeError):
    """Raised when the active audio source cannot be switched safely."""


class AudioSourceController:
    """Enforce the v0.1 INPUT_DEVICE XOR WASAPI_LOOPBACK invariant."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._active_source: AudioSource | None = None

    @property
    def active_source(self) -> AudioSource | None:
        with self._lock:
            return self._active_source

    def start(self, source: AudioSource) -> None:
        with self._lock:
            if self._active_source is not None:
                raise AudioSourceSwitchError(
                    "已有音訊來源正在執行或尚未完整釋放；請先停止再切換。"
                )
            self._active_source = source
            try:
                source.start()
            except Exception as exc:
                raise AudioSourceSwitchError(
                    "無法啟動新的音訊來源；已保留來源供安全停止後重試。"
                ) from exc

    def stop(self) -> None:
        with self._lock:
            source = self._active_source
            if source is None:
                return
            try:
                source.stop()
            except Exception as exc:
                raise AudioSourceSwitchError(
                    "音訊來源無法完整停止，已禁止切換以避免同時擷取。"
                ) from exc
            self._active_source = None

    def switch(self, source: AudioSource) -> None:
        with self._lock:
            self.stop()
            self.start(source)
