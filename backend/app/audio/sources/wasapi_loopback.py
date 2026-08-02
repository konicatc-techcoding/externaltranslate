from __future__ import annotations

import importlib
import time
from collections.abc import Callable
from typing import Any, Protocol

import numpy as np

from backend.app.audio.models import (
    AudioDeviceInfo,
    AudioFormat,
    CaptureStats,
    InputSelection,
    LoopbackEndpointInfo,
    LoopbackSelection,
    MeterReading,
)
from backend.app.audio.sources.input_device import (
    AudioCallback,
    AudioCaptureError,
    InputDeviceSource,
    InputStream,
    InputStreamFactory,
)


class LoopbackDeviceError(RuntimeError):
    """Raised when WASAPI render endpoints cannot be enumerated or selected."""


class LoopbackDeviceBackend(Protocol):
    def list_loopback_devices(self) -> list[dict[str, Any]]: ...

    def get_default_loopback_device(self) -> dict[str, Any]: ...

    def check_loopback_format(
        self, *, device: int, channels: int, rate: int
    ) -> None: ...


class PyAudioWPatchDeviceBackend:
    def __init__(self) -> None:
        self._pyaudio: Any = importlib.import_module("pyaudiowpatch")

    def list_loopback_devices(self) -> list[dict[str, Any]]:
        with self._pyaudio.PyAudio() as manager:
            return [dict(item) for item in manager.get_loopback_device_info_generator()]

    def get_default_loopback_device(self) -> dict[str, Any]:
        with self._pyaudio.PyAudio() as manager:
            return dict(manager.get_default_wasapi_loopback())

    def check_loopback_format(
        self, *, device: int, channels: int, rate: int
    ) -> None:
        with self._pyaudio.PyAudio() as manager:
            manager.is_format_supported(
                rate,
                input_device=device,
                input_channels=channels,
                input_format=self._pyaudio.paFloat32,
            )


class _PyAudioLoopbackStream:
    def __init__(self, manager: Any, stream: Any) -> None:
        self._manager = manager
        self._stream = stream
        self._native_closed = False
        self._manager_terminated = False

    @property
    def active(self) -> bool:
        if self._native_closed or self._manager_terminated:
            return False
        return bool(self._stream.is_active())

    def start(self) -> None:
        if self._native_closed or self._manager_terminated:
            raise RuntimeError("WASAPI loopback stream 已關閉。")
        self._stream.start_stream()

    def stop(self) -> None:
        if (
            not self._native_closed
            and not self._manager_terminated
            and self._stream.is_active()
        ):
            self._stream.stop_stream()

    def close(self) -> None:
        if self._native_closed and self._manager_terminated:
            return
        close_error: Exception | None = None
        try:
            if not self._native_closed:
                self._stream.close()
                self._native_closed = True
        except Exception as exc:
            close_error = exc
        finally:
            if not self._manager_terminated:
                try:
                    self._manager.terminate()
                except Exception:
                    if close_error is None:
                        raise
                else:
                    self._manager_terminated = True
        if close_error is not None:
            raise close_error


class _MalformedNativeFrames:
    """Force malformed native payloads through InputDeviceSource callback isolation."""

    def __init__(self, cause: Exception) -> None:
        self._cause = cause

    def __array__(self, dtype: object = None, copy: object = None) -> object:
        del dtype, copy
        raise ValueError("malformed WASAPI native payload") from self._cause


class PyAudioLoopbackStreamFactory:
    def __init__(self, pyaudio_module: Any | None = None) -> None:
        self._pyaudio: Any = pyaudio_module or importlib.import_module(
            "pyaudiowpatch"
        )
        self._pending_manager: Any | None = None

    @property
    def cleanup_pending(self) -> bool:
        return self._pending_manager is not None

    def retry_pending_cleanup(self) -> None:
        manager = self._pending_manager
        if manager is None:
            return
        manager.terminate()
        self._pending_manager = None

    def open_input_stream(
        self,
        *,
        device: int,
        channels: int,
        samplerate: int,
        dtype: str,
        callback: AudioCallback,
    ) -> InputStream:
        if dtype != "float32":
            raise ValueError("PyAudioWPatch loopback 僅支援 float32 adapter format。")
        if self._pending_manager is not None:
            raise RuntimeError("前次 PyAudio manager 尚未完整釋放。")
        manager = self._pyaudio.PyAudio()

        def bridge(
            in_data: bytes | None,
            frame_count: int,
            time_info: object,
            status_flags: object,
        ) -> tuple[None, int]:
            frames: Any
            try:
                if in_data is None or frame_count < 0:
                    raise ValueError("missing payload or invalid frame count")
                values = np.frombuffer(in_data, dtype=np.float32)
                expected = frame_count * channels
                if values.size != expected:
                    raise ValueError("payload size does not match frame/channel count")
                frames = values.reshape(frame_count, channels)
            except Exception as exc:
                frames = _MalformedNativeFrames(exc)
            try:
                callback(frames, frame_count, time_info, status_flags)
            except Exception:
                return None, int(
                    getattr(self._pyaudio, "paAbort", self._pyaudio.paContinue)
                )
            return None, int(self._pyaudio.paContinue)

        try:
            stream = manager.open(
                format=self._pyaudio.paFloat32,
                channels=channels,
                rate=samplerate,
                input=True,
                input_device_index=device,
                frames_per_buffer=0,
                stream_callback=bridge,
                start=False,
            )
        except Exception as open_error:
            try:
                manager.terminate()
            except Exception as terminate_error:
                self._pending_manager = manager
                raise open_error from terminate_error
            raise
        return _PyAudioLoopbackStream(manager, stream)


def enumerate_loopback_endpoints(
    backend: LoopbackDeviceBackend | None = None,
) -> list[LoopbackEndpointInfo]:
    selected_backend = backend or PyAudioWPatchDeviceBackend()
    try:
        default_index = int(selected_backend.get_default_loopback_device()["index"])
        raw_devices = selected_backend.list_loopback_devices()
        endpoints: list[LoopbackEndpointInfo] = []
        for raw in raw_devices:
            if not bool(raw.get("isLoopbackDevice")):
                continue
            channels = int(raw.get("maxInputChannels", 0))
            sample_rate = int(float(raw.get("defaultSampleRate", 0)))
            if channels <= 0 or sample_rate <= 0:
                continue
            name = str(raw.get("name", "")).removesuffix(" [Loopback]")
            endpoints.append(
                LoopbackEndpointInfo(
                    index=int(raw["index"]),
                    name=name,
                    host_api="Windows WASAPI",
                    channels=channels,
                    default_sample_rate=sample_rate,
                    low_input_latency=float(raw.get("defaultLowInputLatency", 0.0)),
                    is_default=int(raw["index"]) == default_index,
                )
            )
        return endpoints
    except Exception as exc:
        raise LoopbackDeviceError(
            "無法列舉 Windows WASAPI loopback endpoints；"
            "請確認 Windows 音訊服務與輸出裝置可用。"
        ) from exc


def resolve_loopback_selection(
    backend: LoopbackDeviceBackend | None = None,
    *,
    endpoint_index: int | None,
) -> LoopbackSelection:
    selected_backend = backend or PyAudioWPatchDeviceBackend()
    endpoints = enumerate_loopback_endpoints(selected_backend)
    endpoint = next(
        (
            item
            for item in endpoints
            if item.index == endpoint_index
            or (endpoint_index is None and item.is_default)
        ),
        None,
    )
    if endpoint is None:
        requested = "Windows default output" if endpoint_index is None else endpoint_index
        raise LoopbackDeviceError(
            f"找不到 WASAPI loopback endpoint：{requested}；"
            "請重新列舉輸出裝置後再選擇。"
        )
    try:
        selected_backend.check_loopback_format(
            device=endpoint.index,
            channels=endpoint.channels,
            rate=endpoint.default_sample_rate,
        )
    except Exception as exc:
        raise LoopbackDeviceError(
            f"WASAPI loopback endpoint 無法使用 shared-mode native format：{endpoint.name}。"
        ) from exc
    return LoopbackSelection(
        endpoint=endpoint,
        native_format=AudioFormat(
            endpoint.default_sample_rate,
            endpoint.channels,
            "float32",
        ),
    )


class LoopbackCaptureError(RuntimeError):
    """Raised when a WASAPI render endpoint cannot be captured safely."""


class WasapiLoopbackSource:
    """Resolve a render endpoint at Start and capture its shared-mode system mix."""

    def __init__(
        self,
        *,
        endpoint_index: int | None,
        device_backend: LoopbackDeviceBackend | None = None,
        stream_factory: InputStreamFactory | None = None,
        raw_queue_capacity: int = 32,
        pcm_queue_capacity: int = 50,
        default_endpoint_poll_interval: float = 0.25,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if default_endpoint_poll_interval <= 0:
            raise ValueError("default_endpoint_poll_interval 必須大於 0。")
        self._endpoint_index = endpoint_index
        self._device_backend = device_backend or PyAudioWPatchDeviceBackend()
        self._stream_factory = stream_factory or PyAudioLoopbackStreamFactory()
        self._raw_queue_capacity = raw_queue_capacity
        self._pcm_queue_capacity = pcm_queue_capacity
        self._default_endpoint_poll_interval = default_endpoint_poll_interval
        self._clock = clock
        self._next_default_endpoint_poll = 0.0
        self._delegate: InputDeviceSource | None = None
        self._last_delegate: InputDeviceSource | None = None
        self._selection: LoopbackSelection | None = None

    @property
    def active(self) -> bool:
        return self._delegate is not None and self._delegate.active

    @property
    def latest_meter(self) -> MeterReading:
        delegate = self._delegate or self._last_delegate
        return (
            delegate.latest_meter
            if delegate is not None
            else MeterReading(0.0, 0.0, -120.0, -120.0, False)
        )

    @property
    def stats(self) -> CaptureStats:
        delegate = self._delegate or self._last_delegate
        return (
            delegate.stats
            if delegate is not None
            else CaptureStats(0, 0, 0, 0, 0, 0, 0)
        )

    @property
    def selection(self) -> LoopbackSelection | None:
        return self._selection

    def start(self) -> None:
        if self._delegate is not None:
            raise LoopbackCaptureError("WASAPI loopback 擷取已在執行或尚未完整釋放。")
        try:
            selection = resolve_loopback_selection(
                self._device_backend,
                endpoint_index=self._endpoint_index,
            )
            endpoint = selection.endpoint
            input_selection = InputSelection(
                device=AudioDeviceInfo(
                    index=endpoint.index,
                    name=endpoint.name,
                    host_api=endpoint.host_api,
                    max_input_channels=endpoint.channels,
                    default_sample_rate=endpoint.default_sample_rate,
                    low_input_latency=endpoint.low_input_latency,
                    source_kind=endpoint.source_kind,
                ),
                channel=None,
                stream_channels=endpoint.channels,
                native_format=selection.native_format,
            )
            delegate = InputDeviceSource(
                input_selection,
                stream_factory=self._stream_factory,
                raw_queue_capacity=self._raw_queue_capacity,
                pcm_queue_capacity=self._pcm_queue_capacity,
            )
            self._delegate = delegate
            self._selection = selection
            delegate.start()
            self._next_default_endpoint_poll = self._clock()
        except (AudioCaptureError, LoopbackDeviceError) as exc:
            failed_delegate = self._delegate
            if failed_delegate is not None and not failed_delegate.cleanup_pending:
                self._last_delegate = failed_delegate
                self._delegate = None
            raise LoopbackCaptureError(
                "無法啟動 WASAPI loopback；請確認輸出 endpoint 存在、"
                "Windows 音訊服務正常，且沒有程式以 exclusive mode 占用裝置。"
            ) from exc

    def stop(self) -> None:
        delegate = self._delegate
        if delegate is None:
            return
        try:
            delegate.stop()
        except AudioCaptureError as exc:
            raise LoopbackCaptureError(
                "停止 WASAPI loopback 時無法完整釋放 endpoint；請關閉占用程式後重試。"
            ) from exc
        self._last_delegate = delegate
        self._delegate = None

    def get_pcm_chunk(self, timeout: float) -> bytes:
        delegate = self._delegate or self._last_delegate
        if delegate is None:
            raise LoopbackCaptureError("WASAPI loopback 尚未啟動。")
        if self._delegate is not None and self._endpoint_index is None:
            return self._get_pcm_chunk_with_default_endpoint_poll(delegate, timeout)
        try:
            return delegate.get_pcm_chunk(timeout)
        except AudioCaptureError as exc:
            raise LoopbackCaptureError(
                "WASAPI loopback stream 已停止；請檢查預設輸出切換、"
                "裝置拔除或 exclusive-mode 占用。"
            ) from exc

    def _get_pcm_chunk_with_default_endpoint_poll(
        self,
        delegate: InputDeviceSource,
        timeout: float,
    ) -> bytes:
        deadline = self._clock() + timeout
        while True:
            now = self._clock()
            if now >= self._next_default_endpoint_poll:
                self._raise_if_default_endpoint_changed()
                self._next_default_endpoint_poll = (
                    now + self._default_endpoint_poll_interval
                )
            remaining = deadline - now
            if remaining <= 0:
                raise TimeoutError
            wait_timeout = min(
                remaining,
                max(0.0, self._next_default_endpoint_poll - now),
            )
            try:
                return delegate.get_pcm_chunk(wait_timeout)
            except TimeoutError:
                continue
            except AudioCaptureError as exc:
                raise LoopbackCaptureError(
                    "WASAPI loopback stream 已停止；請檢查預設輸出切換、"
                    "裝置拔除或 exclusive-mode 占用。"
                ) from exc

    def _raise_if_default_endpoint_changed(self) -> None:
        if self._endpoint_index is not None or self._selection is None:
            return
        try:
            current_index = int(
                self._device_backend.get_default_loopback_device()["index"]
            )
        except Exception as exc:
            raise LoopbackCaptureError(
                "無法確認目前 Windows 預設輸出 endpoint；請停止後重新開始擷取。"
            ) from exc
        if current_index != self._selection.endpoint.index:
            try:
                self.stop()
            except LoopbackCaptureError as exc:
                raise LoopbackCaptureError(
                    "Windows 預設輸出已變更，但 WASAPI loopback 尚未完整釋放；"
                    "請再次停止擷取後再重新開始。"
                ) from exc
            raise LoopbackCaptureError(
                "Windows 預設輸出已變更，WASAPI loopback 已停止；請重新開始擷取。"
            )
