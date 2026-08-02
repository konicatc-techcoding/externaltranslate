from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import numpy as np
import pytest

from backend.app.audio.models import AudioDeviceInfo, AudioFormat, InputSelection
from backend.app.audio.sources.input_device import AudioCaptureError, InputDeviceSource

AudioCallback = Callable[[np.ndarray[Any, Any], int, object, object], None]


class FakeInputStream:
    def __init__(
        self,
        callback: AudioCallback,
        *,
        fail_start: bool = False,
        fail_stop_once: bool = False,
        fail_close_once: bool = False,
        fail_active_query: bool = False,
    ) -> None:
        self.callback = callback
        self.fail_start = fail_start
        self.fail_stop_once = fail_stop_once
        self.fail_close_once = fail_close_once
        self.fail_active_query = fail_active_query
        self._active = False
        self.closed = False
        self.stop_calls = 0

    @property
    def active(self) -> bool:
        if self.fail_active_query:
            raise RuntimeError("native status query failed")
        return self._active

    @active.setter
    def active(self, value: bool) -> None:
        self._active = value

    def start(self) -> None:
        if self.fail_start:
            raise RuntimeError("device busy")
        self.active = True

    def stop(self) -> None:
        self.stop_calls += 1
        if self.fail_stop_once:
            self.fail_stop_once = False
            raise RuntimeError("stop failed")
        self.active = False

    def close(self) -> None:
        if self.fail_close_once:
            self.fail_close_once = False
            raise RuntimeError("close failed")
        self.closed = True
        self.active = False

    def push(self, frames: np.ndarray[Any, Any], status: object = None) -> None:
        self.callback(frames, len(frames), object(), status)


class FakeStreamFactory:
    def __init__(
        self,
        *,
        fail_start: bool = False,
        fail_stop_once: bool = False,
        fail_close_once: bool = False,
        fail_active_query: bool = False,
    ) -> None:
        self.fail_start = fail_start
        self.fail_stop_once = fail_stop_once
        self.fail_close_once = fail_close_once
        self.fail_active_query = fail_active_query
        self.streams: list[FakeInputStream] = []
        self.settings: list[dict[str, object]] = []

    def open_input_stream(
        self,
        *,
        device: int,
        channels: int,
        samplerate: int,
        dtype: str,
        callback: AudioCallback,
    ) -> FakeInputStream:
        self.settings.append(
            {
                "device": device,
                "channels": channels,
                "samplerate": samplerate,
                "dtype": dtype,
            }
        )
        stream = FakeInputStream(
            callback,
            fail_start=self.fail_start,
            fail_stop_once=self.fail_stop_once,
            fail_close_once=self.fail_close_once,
            fail_active_query=self.fail_active_query,
        )
        self.fail_stop_once = False
        self.fail_close_once = False
        self.streams.append(stream)
        return stream


def make_input_selection(sample_rate: int = 16000) -> InputSelection:
    device = AudioDeviceInfo(
        index=14,
        name="Test Interface Input",
        host_api="Windows WASAPI",
        max_input_channels=2,
        default_sample_rate=sample_rate,
        low_input_latency=0.003,
    )
    return InputSelection(
        device=device,
        channel=1,
        stream_channels=1,
        native_format=AudioFormat(sample_rate, 1, "float32"),
    )


def test_capture_callback_hands_frames_to_worker_and_emits_pcm_chunk() -> None:
    factory = FakeStreamFactory()
    source = InputDeviceSource(make_input_selection(), stream_factory=factory)

    source.start()
    factory.streams[0].push(np.full((1600, 1), 0.25, dtype=np.float32))
    chunk = source.get_pcm_chunk(timeout=1.0)
    source.stop()

    assert len(chunk) == 3200
    assert np.all(np.frombuffer(chunk, dtype="<i2") == 8192)
    assert source.latest_meter.peak == pytest.approx(0.25)
    assert source.stats.callback_blocks == 1
    assert source.stats.pcm_chunks == 1
    assert factory.settings == [
        {
            "device": 14,
            "channels": 1,
            "samplerate": 16000,
            "dtype": "float32",
        }
    ]
    assert factory.streams[0].closed is True


def test_capture_can_start_and_stop_repeatedly_without_reusing_stream() -> None:
    factory = FakeStreamFactory()
    source = InputDeviceSource(make_input_selection(), stream_factory=factory)

    source.start()
    source.stop()
    source.start()
    source.stop()

    assert len(factory.streams) == 2
    assert all(stream.closed for stream in factory.streams)
    assert source.active is False


def test_capture_maps_stream_start_failure_and_closes_handle() -> None:
    factory = FakeStreamFactory(fail_start=True)
    source = InputDeviceSource(make_input_selection(), stream_factory=factory)

    with pytest.raises(AudioCaptureError, match="無法啟動音訊擷取"):
        source.start()

    assert factory.streams[0].closed is True
    assert source.active is False


def test_capture_retains_failed_start_stream_when_close_must_be_retried() -> None:
    factory = FakeStreamFactory(fail_start=True, fail_close_once=True)
    source = InputDeviceSource(make_input_selection(), stream_factory=factory)

    with pytest.raises(AudioCaptureError, match="無法啟動音訊擷取"):
        source.start()

    assert factory.streams[0].closed is False
    with pytest.raises(AudioCaptureError, match="前次音訊裝置尚未完整釋放"):
        source.start()

    source.stop()

    assert factory.streams[0].closed is True


def test_capture_callback_isolates_copy_failure() -> None:
    class BadFrames:
        def __array__(self, dtype: object = None, copy: object = None) -> object:
            raise RuntimeError("copy failed")

    factory = FakeStreamFactory()
    source = InputDeviceSource(make_input_selection(), stream_factory=factory)
    source.start()

    factory.streams[0].callback(BadFrames(), 1, object(), object())  # type: ignore[arg-type]
    with pytest.raises(AudioCaptureError, match="callback 無法接收資料"):
        source.get_pcm_chunk(timeout=0.01)
    source.stop()

    assert source.stats.callback_errors == 1
    assert source.stats.status_events == 1


def test_capture_reports_unexpected_device_stop_as_actionable_error() -> None:
    factory = FakeStreamFactory()
    source = InputDeviceSource(make_input_selection(), stream_factory=factory)
    source.start()
    factory.streams[0].active = False

    with pytest.raises(AudioCaptureError, match="音訊輸入裝置已停止"):
        source.get_pcm_chunk(timeout=0.01)

    source.stop()


def test_capture_reports_processing_failure_instead_of_generic_timeout() -> None:
    factory = FakeStreamFactory()
    source = InputDeviceSource(make_input_selection(), stream_factory=factory)
    source.start()
    factory.streams[0].push(np.zeros((160, 2), dtype=np.float32))

    with pytest.raises(AudioCaptureError, match="音訊處理失敗"):
        source.get_pcm_chunk(timeout=0.2)

    source.stop()


def test_capture_blocks_restart_while_previous_worker_is_still_alive() -> None:
    release_worker = threading.Event()

    def stuck_worker() -> None:
        release_worker.wait()

    factory = FakeStreamFactory()
    source = InputDeviceSource(
        make_input_selection(),
        stream_factory=factory,
        worker_join_timeout=0.01,
    )
    source._worker_loop = stuck_worker  # type: ignore[method-assign]
    source.start()

    with pytest.raises(AudioCaptureError, match="無法完整釋放"):
        source.stop()
    with pytest.raises(AudioCaptureError, match="上一個音訊 worker 尚未停止"):
        source.start()

    release_worker.set()
    source.stop()
    source.start()
    source.stop()


def test_capture_retries_failed_stream_close_before_allowing_restart() -> None:
    factory = FakeStreamFactory(fail_close_once=True)
    source = InputDeviceSource(make_input_selection(), stream_factory=factory)
    source.start()

    with pytest.raises(AudioCaptureError, match="無法完整釋放"):
        source.stop()
    assert factory.streams[0].closed is False
    with pytest.raises(AudioCaptureError, match="前次音訊裝置尚未完整釋放"):
        source.start()

    source.stop()
    assert factory.streams[0].closed is True
    source.start()
    source.stop()


def test_capture_requires_explicit_stop_retry_after_stop_fails_but_close_succeeds() -> None:
    factory = FakeStreamFactory(fail_stop_once=True)
    source = InputDeviceSource(make_input_selection(), stream_factory=factory)
    source.start()

    with pytest.raises(AudioCaptureError, match="無法完整釋放"):
        source.stop()

    assert factory.streams[0].closed is True
    assert source.cleanup_pending is True
    with pytest.raises(AudioCaptureError, match="尚未完整釋放"):
        source.start()

    source.stop()
    assert source.cleanup_pending is False
    source.start()
    source.stop()


def test_capture_maps_native_status_query_failure_and_preserves_cleanup_ownership() -> None:
    factory = FakeStreamFactory(fail_active_query=True)
    source = InputDeviceSource(make_input_selection(), stream_factory=factory)
    source.start()

    assert source.active is False
    assert source.cleanup_pending is True
    with pytest.raises(AudioCaptureError, match="無法確認音訊輸入裝置狀態"):
        source.get_pcm_chunk(timeout=0.01)
    with pytest.raises(AudioCaptureError, match="尚未停止|尚未完整釋放"):
        source.start()

    source.stop()
    assert source.cleanup_pending is False
    factory.fail_active_query = False
    source.start()
    source.stop()


def test_capture_maps_status_query_failure_encountered_after_pcm_timeout() -> None:
    factory = FakeStreamFactory()
    source = InputDeviceSource(make_input_selection(), stream_factory=factory)
    source.start()
    factory.streams[0].fail_active_query = True

    with pytest.raises(AudioCaptureError, match="無法確認音訊輸入裝置狀態"):
        source.get_pcm_chunk(timeout=0.01)

    assert source.active is False
    assert source.cleanup_pending is True
    source.stop()
