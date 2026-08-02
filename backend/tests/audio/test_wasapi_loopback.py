from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pytest

from backend.app.audio.models import AudioSourceKind
from backend.app.audio.sources.wasapi_loopback import (
    LoopbackCaptureError,
    LoopbackDeviceError,
    PyAudioLoopbackStreamFactory,
    WasapiLoopbackSource,
    enumerate_loopback_endpoints,
    resolve_loopback_selection,
)

AudioCallback = Callable[[np.ndarray[Any, Any], int, object, object], None]


class FakeLoopbackStream:
    def __init__(
        self,
        callback: AudioCallback,
        *,
        fail_start: bool = False,
        fail_stop_once: bool = False,
        fail_close_once: bool = False,
    ) -> None:
        self.callback = callback
        self.fail_start = fail_start
        self.fail_stop_once = fail_stop_once
        self.fail_close_once = fail_close_once
        self.active = False
        self.closed = False

    def start(self) -> None:
        if self.fail_start:
            raise RuntimeError("start failed")
        self.active = True

    def stop(self) -> None:
        if self.fail_stop_once:
            self.fail_stop_once = False
            raise RuntimeError("stop failed")
        self.active = False

    def close(self) -> None:
        if self.fail_close_once:
            self.fail_close_once = False
            raise RuntimeError("close failed")
        self.active = False
        self.closed = True

    def push(self, frames: np.ndarray[Any, Any], status: object = None) -> None:
        self.callback(frames, len(frames), object(), status)


class FakeLoopbackStreamFactory:
    def __init__(
        self,
        *,
        fail_start_once: bool = False,
        fail_stop_once: bool = False,
        fail_close_once: bool = False,
    ) -> None:
        self.streams: list[FakeLoopbackStream] = []
        self.settings: list[dict[str, object]] = []
        self.fail_start_once = fail_start_once
        self.fail_stop_once = fail_stop_once
        self.fail_close_once = fail_close_once

    def open_input_stream(
        self,
        *,
        device: int,
        channels: int,
        samplerate: int,
        dtype: str,
        callback: AudioCallback,
    ) -> FakeLoopbackStream:
        self.settings.append(
            {
                "device": device,
                "channels": channels,
                "samplerate": samplerate,
                "dtype": dtype,
            }
        )
        stream = FakeLoopbackStream(
            callback,
            fail_start=self.fail_start_once,
            fail_stop_once=self.fail_stop_once,
            fail_close_once=self.fail_close_once,
        )
        self.fail_start_once = False
        self.fail_stop_once = False
        self.fail_close_once = False
        self.streams.append(stream)
        return stream


class FakeLoopbackBackend:
    def __init__(self) -> None:
        self.checked: list[dict[str, int]] = []
        self.default_index = 16

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
            },
            {
                "index": 17,
                "name": "Test Monitor Output [Loopback]",
                "hostApi": 2,
                "maxInputChannels": 2,
                "defaultSampleRate": 48000.0,
                "defaultLowInputLatency": 0.003,
                "isLoopbackDevice": True,
            },
        ]

    def get_default_loopback_device(self) -> dict[str, Any]:
        return next(
            item
            for item in self.list_loopback_devices()
            if item["index"] == self.default_index
        )

    def check_loopback_format(self, *, device: int, channels: int, rate: int) -> None:
        self.checked.append({"device": device, "channels": channels, "rate": rate})


def test_loopback_enumeration_keeps_render_endpoint_identity() -> None:
    endpoints = enumerate_loopback_endpoints(FakeLoopbackBackend())

    assert [endpoint.index for endpoint in endpoints] == [16, 17]
    assert endpoints[0].name == "Test Speakers"
    assert endpoints[0].host_api == "Windows WASAPI"
    assert endpoints[0].channels == 2
    assert endpoints[0].default_sample_rate == 48000
    assert endpoints[0].is_default is True
    assert endpoints[0].source_kind is AudioSourceKind.WASAPI_LOOPBACK


def test_loopback_default_is_resolved_when_selection_is_started() -> None:
    backend = FakeLoopbackBackend()

    selection = resolve_loopback_selection(backend, endpoint_index=None)

    assert selection.endpoint.index == 16
    assert selection.native_format.channels == 2
    assert selection.native_format.dtype == "float32"
    assert backend.checked == [{"device": 16, "channels": 2, "rate": 48000}]


def test_loopback_explicit_endpoint_is_validated() -> None:
    backend = FakeLoopbackBackend()

    selection = resolve_loopback_selection(backend, endpoint_index=17)

    assert selection.endpoint.index == 17
    assert backend.checked == [{"device": 17, "channels": 2, "rate": 48000}]


def test_loopback_selection_rejects_unknown_endpoint() -> None:
    with pytest.raises(LoopbackDeviceError, match="找不到 WASAPI loopback endpoint"):
        resolve_loopback_selection(FakeLoopbackBackend(), endpoint_index=999)


def test_loopback_source_reuses_meter_converter_and_bounded_pcm_contract() -> None:
    backend = FakeLoopbackBackend()
    factory = FakeLoopbackStreamFactory()
    source = WasapiLoopbackSource(
        endpoint_index=None,
        device_backend=backend,
        stream_factory=factory,
    )
    frames = np.column_stack(
        (
            np.full(48000, 0.25, dtype=np.float32),
            np.full(48000, -0.125, dtype=np.float32),
        )
    )

    source.start()
    factory.streams[0].push(frames)
    chunk = source.get_pcm_chunk(timeout=1.0)
    source.stop()

    samples = np.frombuffer(chunk, dtype="<i2")
    assert samples.shape == (1600,)
    assert np.median(samples[100:]) == pytest.approx(2048, abs=2)
    assert source.latest_meter.peak == pytest.approx(0.0625)
    assert source.stats.callback_blocks == 1
    assert factory.settings == [
        {
            "device": 16,
            "channels": 2,
            "samplerate": 48000,
            "dtype": "float32",
        }
    ]
    assert factory.streams[0].closed is True


def test_loopback_source_resolves_windows_default_on_every_start() -> None:
    backend = FakeLoopbackBackend()
    factory = FakeLoopbackStreamFactory()
    source = WasapiLoopbackSource(
        endpoint_index=None,
        device_backend=backend,
        stream_factory=factory,
    )

    source.start()
    assert source.selection is not None
    assert source.selection.endpoint.index == 16
    source.stop()

    backend.default_index = 17
    source.start()
    assert source.selection is not None
    assert source.selection.endpoint.index == 17
    source.stop()

    assert [settings["device"] for settings in factory.settings] == [16, 17]


def test_loopback_failed_delegate_start_can_restart_after_successful_cleanup() -> None:
    factory = FakeLoopbackStreamFactory(fail_start_once=True)
    source = WasapiLoopbackSource(
        endpoint_index=16,
        device_backend=FakeLoopbackBackend(),
        stream_factory=factory,
    )

    with pytest.raises(LoopbackCaptureError, match="無法啟動 WASAPI loopback"):
        source.start()

    assert factory.streams[0].closed is True
    source.start()
    source.stop()

    assert len(factory.streams) == 2


def test_loopback_failed_delegate_cleanup_is_retained_for_explicit_stop() -> None:
    factory = FakeLoopbackStreamFactory(
        fail_start_once=True,
        fail_close_once=True,
    )
    source = WasapiLoopbackSource(
        endpoint_index=16,
        device_backend=FakeLoopbackBackend(),
        stream_factory=factory,
    )

    with pytest.raises(LoopbackCaptureError, match="無法啟動 WASAPI loopback"):
        source.start()
    with pytest.raises(LoopbackCaptureError, match="尚未完整釋放"):
        source.start()

    source.stop()
    assert factory.streams[0].closed is True
    source.start()
    source.stop()


def test_loopback_source_stops_when_windows_default_changes() -> None:
    backend = FakeLoopbackBackend()
    source = WasapiLoopbackSource(
        endpoint_index=None,
        device_backend=backend,
        stream_factory=FakeLoopbackStreamFactory(),
    )
    source.start()
    backend.default_index = 17

    with pytest.raises(LoopbackCaptureError, match="預設輸出已變更"):
        source.get_pcm_chunk(timeout=0.01)

    assert source.active is False


def test_loopback_polls_default_change_even_when_pcm_is_available() -> None:
    class FakeClock:
        now = 0.0

        def __call__(self) -> float:
            return self.now

    backend = FakeLoopbackBackend()
    factory = FakeLoopbackStreamFactory()
    clock = FakeClock()
    source = WasapiLoopbackSource(
        endpoint_index=None,
        device_backend=backend,
        stream_factory=factory,
        default_endpoint_poll_interval=0.25,
        clock=clock,
    )
    source.start()
    factory.streams[0].push(np.zeros((48000, 2), dtype=np.float32))
    assert len(source.get_pcm_chunk(timeout=1.0)) == 3200

    factory.streams[0].push(np.zeros((48000, 2), dtype=np.float32))
    backend.default_index = 17
    clock.now = 0.25

    with pytest.raises(LoopbackCaptureError, match="預設輸出已變更.*已停止"):
        source.get_pcm_chunk(timeout=1.0)

    assert source.active is False


def test_loopback_default_change_reports_incomplete_release_when_stop_fails() -> None:
    backend = FakeLoopbackBackend()
    factory = FakeLoopbackStreamFactory(fail_stop_once=True)
    source = WasapiLoopbackSource(
        endpoint_index=None,
        device_backend=backend,
        stream_factory=factory,
        default_endpoint_poll_interval=0.01,
    )
    source.start()
    backend.default_index = 17

    with pytest.raises(LoopbackCaptureError, match="尚未完整釋放"):
        source.get_pcm_chunk(timeout=0.02)

    source.stop()
    source.start()
    source.stop()


def test_explicit_loopback_endpoint_ignores_default_endpoint_change() -> None:
    backend = FakeLoopbackBackend()
    source = WasapiLoopbackSource(
        endpoint_index=16,
        device_backend=backend,
        stream_factory=FakeLoopbackStreamFactory(),
    )
    source.start()
    backend.default_index = 17

    with pytest.raises(TimeoutError):
        source.get_pcm_chunk(timeout=0.01)

    assert source.active is True
    source.stop()


def test_loopback_source_propagates_malformed_native_frames() -> None:
    factory = FakeLoopbackStreamFactory()
    source = WasapiLoopbackSource(
        endpoint_index=16,
        device_backend=FakeLoopbackBackend(),
        stream_factory=factory,
    )
    source.start()
    factory.streams[0].push(np.empty((480, 0), dtype=np.float32))

    with pytest.raises(LoopbackCaptureError, match="stream 已停止"):
        source.get_pcm_chunk(timeout=1.0)

    assert source.stats.processing_errors == 1
    source.stop()


def test_pyaudio_stream_factory_bridges_float32_and_releases_manager() -> None:
    captured: list[np.ndarray[Any, Any]] = []

    class NativeStream:
        def __init__(self) -> None:
            self.started = False
            self.closed = False

        def is_active(self) -> bool:
            return self.started and not self.closed

        def start_stream(self) -> None:
            self.started = True

        def stop_stream(self) -> None:
            self.started = False

        def close(self) -> None:
            self.closed = True

    class Manager:
        def __init__(self) -> None:
            self.stream = NativeStream()
            self.settings: dict[str, Any] = {}
            self.terminated = False

        def open(self, **settings: Any) -> NativeStream:
            self.settings = settings
            return self.stream

        def terminate(self) -> None:
            self.terminated = True

    class Module:
        paFloat32 = 1
        paContinue = 0

        def __init__(self) -> None:
            self.manager = Manager()

        def PyAudio(self) -> Manager:
            return self.manager

    module = Module()
    factory = PyAudioLoopbackStreamFactory(module)
    stream = factory.open_input_stream(
        device=16,
        channels=2,
        samplerate=48000,
        dtype="float32",
        callback=lambda frames, _count, _time, _status: captured.append(frames.copy()),
    )
    native_callback = module.manager.settings["stream_callback"]
    payload = np.full((480, 2), 0.125, dtype=np.float32)

    stream.start()
    result = native_callback(payload.tobytes(), 480, object(), 0)
    stream.stop()
    stream.close()

    assert result == (None, module.paContinue)
    assert len(captured) == 1
    assert np.array_equal(captured[0], payload)
    assert module.manager.settings["start"] is False
    assert module.manager.stream.closed is True
    assert module.manager.terminated is True


def test_pyaudio_stream_terminates_manager_when_native_close_fails() -> None:
    class NativeStream:
        def __init__(self) -> None:
            self.started = True
            self.closed = False
            self.fail_close_once = True

        def is_active(self) -> bool:
            return self.started and not self.closed

        def start_stream(self) -> None:
            self.started = True

        def stop_stream(self) -> None:
            self.started = False

        def close(self) -> None:
            if self.fail_close_once:
                self.fail_close_once = False
                raise RuntimeError("native close failed")
            self.closed = True

    class Manager:
        def __init__(self) -> None:
            self.stream = NativeStream()
            self.terminate_calls = 0

        def open(self, **settings: Any) -> NativeStream:
            del settings
            return self.stream

        def terminate(self) -> None:
            self.terminate_calls += 1

    class Module:
        paFloat32 = 1
        paContinue = 0

        def __init__(self) -> None:
            self.manager = Manager()

        def PyAudio(self) -> Manager:
            return self.manager

    module = Module()
    stream = PyAudioLoopbackStreamFactory(module).open_input_stream(
        device=16,
        channels=2,
        samplerate=48000,
        dtype="float32",
        callback=lambda _frames, _count, _time, _status: None,
    )

    with pytest.raises(RuntimeError, match="native close failed"):
        stream.close()

    assert module.manager.terminate_calls == 1
    assert stream.active is False

    stream.close()
    assert module.manager.stream.closed is True
    assert module.manager.terminate_calls == 1


def test_loopback_retains_manager_when_open_and_initial_terminate_fail() -> None:
    class NativeStream:
        def __init__(self) -> None:
            self.started = False
            self.closed = False

        def is_active(self) -> bool:
            return self.started and not self.closed

        def start_stream(self) -> None:
            self.started = True

        def stop_stream(self) -> None:
            self.started = False

        def close(self) -> None:
            self.closed = True

    class Manager:
        def __init__(self, *, fail_open: bool, fail_terminate_once: bool) -> None:
            self.fail_open = fail_open
            self.fail_terminate_once = fail_terminate_once
            self.stream = NativeStream()
            self.terminate_calls = 0

        def open(self, **settings: Any) -> NativeStream:
            del settings
            if self.fail_open:
                raise RuntimeError("open failed")
            return self.stream

        def terminate(self) -> None:
            self.terminate_calls += 1
            if self.fail_terminate_once:
                self.fail_terminate_once = False
                raise RuntimeError("terminate failed")

    class Module:
        paFloat32 = 1
        paContinue = 0

        def __init__(self) -> None:
            self.managers: list[Manager] = []

        def PyAudio(self) -> Manager:
            manager = Manager(
                fail_open=not self.managers,
                fail_terminate_once=not self.managers,
            )
            self.managers.append(manager)
            return manager

    module = Module()
    source = WasapiLoopbackSource(
        endpoint_index=16,
        device_backend=FakeLoopbackBackend(),
        stream_factory=PyAudioLoopbackStreamFactory(module),
    )

    with pytest.raises(LoopbackCaptureError) as captured:
        source.start()

    delegate_error = captured.value.__cause__
    assert delegate_error is not None
    open_error = delegate_error.__cause__
    assert open_error is not None
    assert str(open_error) == "open failed"
    assert open_error.__cause__ is not None
    assert str(open_error.__cause__) == "terminate failed"
    with pytest.raises(LoopbackCaptureError, match="尚未完整釋放"):
        source.start()
    assert len(module.managers) == 1

    source.stop()
    assert module.managers[0].terminate_calls == 2
    source.start()
    source.stop()
    assert len(module.managers) == 2


@pytest.mark.parametrize(
    ("payload", "frame_count"),
    [
        (b"\x00", 1),
        (None, 1),
        (np.zeros(3, dtype=np.float32).tobytes(), 2),
    ],
)
def test_pyaudio_bridge_routes_malformed_payload_to_callback_failure(
    payload: bytes | None,
    frame_count: int,
) -> None:
    class NativeStream:
        def __init__(self) -> None:
            self.started = False
            self.closed = False

        def is_active(self) -> bool:
            return self.started and not self.closed

        def start_stream(self) -> None:
            self.started = True

        def stop_stream(self) -> None:
            self.started = False

        def close(self) -> None:
            self.closed = True

    class Manager:
        def __init__(self) -> None:
            self.stream = NativeStream()
            self.callback: Callable[..., tuple[None, int]] | None = None

        def open(self, **settings: Any) -> NativeStream:
            self.callback = settings["stream_callback"]
            return self.stream

        def terminate(self) -> None:
            return None

    class Module:
        paFloat32 = 1
        paContinue = 0

        def __init__(self) -> None:
            self.manager = Manager()

        def PyAudio(self) -> Manager:
            return self.manager

    module = Module()
    source = WasapiLoopbackSource(
        endpoint_index=16,
        device_backend=FakeLoopbackBackend(),
        stream_factory=PyAudioLoopbackStreamFactory(module),
    )
    source.start()
    native_callback = module.manager.callback
    assert native_callback is not None

    result = native_callback(payload, frame_count, object(), 0)

    assert result == (None, module.paContinue)
    with pytest.raises(LoopbackCaptureError, match="stream 已停止"):
        source.get_pcm_chunk(timeout=0.01)
    assert source.stats.callback_errors == 1
    assert source.stats.processing_errors == 0
    source.stop()


def test_loopback_maps_native_status_query_failure_and_retries_cleanup() -> None:
    class NativeStream:
        def __init__(self, *, fail_status_query: bool) -> None:
            self.fail_status_query = fail_status_query
            self.started = False
            self.closed = False

        def is_active(self) -> bool:
            if self.fail_status_query:
                raise RuntimeError("native is_active failed")
            return self.started and not self.closed

        def start_stream(self) -> None:
            self.started = True

        def stop_stream(self) -> None:
            self.started = False

        def close(self) -> None:
            self.closed = True

    class Manager:
        def __init__(self, *, fail_status_query: bool) -> None:
            self.stream = NativeStream(fail_status_query=fail_status_query)
            self.terminated = False

        def open(self, **settings: Any) -> NativeStream:
            del settings
            return self.stream

        def terminate(self) -> None:
            self.terminated = True

    class Module:
        paFloat32 = 1
        paContinue = 0

        def __init__(self) -> None:
            self.managers: list[Manager] = []

        def PyAudio(self) -> Manager:
            manager = Manager(fail_status_query=not self.managers)
            self.managers.append(manager)
            return manager

    module = Module()
    source = WasapiLoopbackSource(
        endpoint_index=16,
        device_backend=FakeLoopbackBackend(),
        stream_factory=PyAudioLoopbackStreamFactory(module),
    )
    source.start()

    assert source.active is False
    with pytest.raises(LoopbackCaptureError, match="stream 已停止"):
        source.get_pcm_chunk(timeout=0.01)
    with pytest.raises(LoopbackCaptureError, match="尚未完整釋放"):
        source.start()

    with pytest.raises(LoopbackCaptureError, match="無法完整釋放"):
        source.stop()
    assert module.managers[0].stream.closed is True
    assert module.managers[0].terminated is True
    with pytest.raises(LoopbackCaptureError, match="尚未完整釋放"):
        source.start()

    source.stop()
    source.start()
    source.stop()
    assert len(module.managers) == 2
