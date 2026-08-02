from __future__ import annotations

import importlib
import threading
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

from backend.app.audio.converter import Pcm16ChunkConverter
from backend.app.audio.meter import calculate_meter
from backend.app.audio.models import CaptureStats, InputSelection, MeterReading
from backend.app.audio.queue import DroppingQueue


class AudioCaptureError(RuntimeError):
    """Raised when an input stream cannot start, stop, or release safely."""


class AudioCallback(Protocol):
    def __call__(
        self,
        indata: npt.NDArray[np.float32],
        frames: int,
        time_info: object,
        status: object,
    ) -> None: ...


class InputStream(Protocol):
    @property
    def active(self) -> bool: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def close(self) -> None: ...


class InputStreamFactory(Protocol):
    def open_input_stream(
        self,
        *,
        device: int,
        channels: int,
        samplerate: int,
        dtype: str,
        callback: AudioCallback,
    ) -> InputStream: ...


class SoundDeviceStreamFactory:
    def __init__(self) -> None:
        self._sounddevice: Any = importlib.import_module("sounddevice")

    def open_input_stream(
        self,
        *,
        device: int,
        channels: int,
        samplerate: int,
        dtype: str,
        callback: AudioCallback,
    ) -> InputStream:
        stream: InputStream = self._sounddevice.InputStream(
            device=device,
            channels=channels,
            samplerate=samplerate,
            dtype=dtype,
            blocksize=0,
            latency="high",
            callback=callback,
        )
        return stream


class InputDeviceSource:
    """Non-blocking PortAudio callback with worker-side PCM processing."""

    def __init__(
        self,
        selection: InputSelection,
        *,
        stream_factory: InputStreamFactory | None = None,
        raw_queue_capacity: int = 32,
        pcm_queue_capacity: int = 50,
        worker_join_timeout: float = 2.0,
    ) -> None:
        if worker_join_timeout <= 0:
            raise ValueError("worker_join_timeout 必須大於 0。")
        self._selection = selection
        self._stream_factory = stream_factory or SoundDeviceStreamFactory()
        self._raw_queue_capacity = raw_queue_capacity
        self._pcm_queue_capacity = pcm_queue_capacity
        self._worker_join_timeout = worker_join_timeout
        self._stream: InputStream | None = None
        self._worker: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._raw_queue = DroppingQueue[npt.NDArray[np.float32]](raw_queue_capacity)
        self._pcm_queue = DroppingQueue[bytes](pcm_queue_capacity)
        self._converter: Pcm16ChunkConverter | None = None
        self._active = False
        self._latest_meter = MeterReading(0.0, 0.0, -120.0, -120.0, False)
        self._callback_blocks = 0
        self._callback_errors = 0
        self._status_events = 0
        self._processing_errors = 0
        self._pcm_chunks = 0
        self._callback_failure: Exception | None = None
        self._processing_failure: Exception | None = None
        self._status_failure: Exception | None = None
        self._cleanup_ack_pending = False

    @property
    def active(self) -> bool:
        stream = self._stream
        return (
            self._active
            and stream is not None
            and self._query_stream_active(stream)
        )

    @property
    def cleanup_pending(self) -> bool:
        """Whether this source still owns resources that require a retrying stop."""
        worker = self._worker
        return (
            self._cleanup_ack_pending
            or bool(getattr(self._stream_factory, "cleanup_pending", False))
            or self._stream is not None
            or (worker is not None and worker.is_alive())
        )

    @property
    def latest_meter(self) -> MeterReading:
        return self._latest_meter

    @property
    def stats(self) -> CaptureStats:
        return CaptureStats(
            callback_blocks=self._callback_blocks,
            callback_errors=self._callback_errors,
            status_events=self._status_events,
            processing_errors=self._processing_errors,
            raw_dropped=self._raw_queue.dropped_count,
            pcm_chunks=self._pcm_chunks,
            pcm_dropped=self._pcm_queue.dropped_count,
        )

    def start(self) -> None:
        previous_worker = self._worker
        if previous_worker is not None:
            if previous_worker.is_alive():
                raise AudioCaptureError(
                    "上一個音訊 worker 尚未停止，已禁止重新啟動以避免資源洩漏。"
                )
            self._worker = None
        if self._cleanup_ack_pending or bool(
            getattr(self._stream_factory, "cleanup_pending", False)
        ):
            raise AudioCaptureError(
                "前次音訊裝置尚未完整釋放，已禁止重新啟動；請先再次停止擷取。"
            )
        if self._active:
            raise AudioCaptureError("音訊擷取已在執行中。")
        if self._stream is not None:
            raise AudioCaptureError(
                "前次音訊裝置尚未完整釋放，已禁止重新啟動；請先再次停止擷取。"
            )

        self._reset_run_state()
        native = self._selection.native_format
        self._converter = Pcm16ChunkConverter(
            native.sample_rate,
            native.channels,
            self._selection.channel,
        )
        try:
            stream = self._stream_factory.open_input_stream(
                device=self._selection.device.index,
                channels=self._selection.stream_channels,
                samplerate=native.sample_rate,
                dtype=native.dtype,
                callback=self._audio_callback,
            )
            self._stream = stream
            self._worker = threading.Thread(
                target=self._worker_loop,
                name="externaltranslate-audio-worker",
                daemon=True,
            )
            self._worker.start()
            stream.start()
            self._active = True
        except Exception as exc:
            self._cleanup_failed_start()
            raise AudioCaptureError(
                f"無法啟動音訊擷取：{self._selection.device.name}。"
                "請確認裝置未被獨占、channel 與 sample rate 正確。"
            ) from exc

    def stop(self) -> None:
        stream = self._stream
        cleanup_error: Exception | None = None
        if stream is not None:
            try:
                stream.stop()
            except Exception as exc:
                cleanup_error = exc

        self._active = False
        self._stop_event.set()
        worker = self._worker
        if worker is not None:
            worker.join(timeout=self._worker_join_timeout)
            if worker.is_alive() and cleanup_error is None:
                cleanup_error = RuntimeError("audio worker did not stop")

        stream_closed = stream is None
        if stream is not None:
            try:
                stream.close()
                stream_closed = True
            except Exception as exc:
                if cleanup_error is None:
                    cleanup_error = exc
        if stream_closed:
            self._stream = None
        if worker is None or not worker.is_alive():
            self._worker = None

        retry_factory_cleanup = getattr(
            self._stream_factory, "retry_pending_cleanup", None
        )
        if retry_factory_cleanup is not None:
            try:
                retry_factory_cleanup()
            except Exception as exc:
                if cleanup_error is None:
                    cleanup_error = exc

        if cleanup_error is not None:
            self._cleanup_ack_pending = True
            raise AudioCaptureError(
                "停止音訊擷取時無法完整釋放裝置；請關閉占用裝置的程式後重試。"
            ) from cleanup_error
        self._cleanup_ack_pending = False

    def get_pcm_chunk(self, timeout: float) -> bytes:
        self._raise_pipeline_failure()
        try:
            return self._pcm_queue.get(timeout)
        except TimeoutError:
            self._raise_pipeline_failure()
            stream = self._stream
            if self._active and stream is not None:
                stream_active = self._query_stream_active(stream)
                self._raise_pipeline_failure()
                if not stream_active:
                    self._active = False
                    self._stop_event.set()
                    raise AudioCaptureError(
                        "音訊輸入裝置已停止；請確認 USB 連線、Windows driver 與裝置電源，"
                        "然後重新開始擷取。"
                    ) from None
            raise

    def _reset_run_state(self) -> None:
        self._stop_event = threading.Event()
        self._raw_queue = DroppingQueue(self._raw_queue_capacity)
        self._pcm_queue = DroppingQueue(self._pcm_queue_capacity)
        self._callback_blocks = 0
        self._callback_errors = 0
        self._status_events = 0
        self._processing_errors = 0
        self._pcm_chunks = 0
        self._callback_failure = None
        self._processing_failure = None
        self._status_failure = None
        self._latest_meter = MeterReading(0.0, 0.0, -120.0, -120.0, False)

    def _query_stream_active(self, stream: InputStream) -> bool:
        try:
            return stream.active
        except Exception as exc:
            self._active = False
            self._stop_event.set()
            if self._status_failure is None:
                self._status_failure = exc
            return False

    def _audio_callback(
        self,
        indata: npt.NDArray[np.float32],
        frames: int,
        time_info: object,
        status: object,
    ) -> None:
        del frames, time_info
        if status:
            self._status_events += 1
        try:
            copied = np.array(indata, dtype=np.float32, copy=True)
            self._raw_queue.put_nowait(copied)
            self._callback_blocks += 1
        except Exception as exc:
            self._callback_errors += 1
            if self._callback_failure is None:
                self._callback_failure = exc
            self._stop_event.set()

    def _worker_loop(self) -> None:
        converter = self._converter
        if converter is None:
            return
        while not self._stop_event.is_set() or self._raw_queue.size:
            try:
                frames = self._raw_queue.get(timeout=0.05)
            except TimeoutError:
                continue
            try:
                if (
                    frames.ndim != 2
                    or frames.shape[1] != self._selection.stream_channels
                ):
                    raise ValueError(
                        "音訊 callback frame shape 與 native channel count 不符。"
                    )
                selected = np.ascontiguousarray(
                    np.mean(frames, axis=1, dtype=np.float32)
                    if self._selection.channel is None
                    else frames[:, self._selection.channel - 1],
                    dtype=np.float32,
                )
                self._latest_meter = calculate_meter(selected)
                self._enqueue_pcm(converter.process(frames))
            except Exception as exc:
                self._processing_errors += 1
                if self._processing_failure is None:
                    self._processing_failure = exc
                self._raw_queue.clear()
                self._stop_event.set()
                break
        try:
            self._enqueue_pcm(converter.finish())
        except Exception as exc:
            self._processing_errors += 1
            if self._processing_failure is None:
                self._processing_failure = exc

    def _enqueue_pcm(self, chunks: list[bytes]) -> None:
        for chunk in chunks:
            self._pcm_queue.put_nowait(chunk)
            self._pcm_chunks += 1

    def _raise_pipeline_failure(self) -> None:
        if self._callback_failure is not None:
            raise AudioCaptureError(
                "音訊 callback 無法接收資料；請重新選擇裝置並檢查 Windows driver。"
            ) from self._callback_failure
        if self._processing_failure is not None:
            raise AudioCaptureError(
                "音訊處理失敗；請確認 channel、sample rate 與輸入格式後重新開始。"
            ) from self._processing_failure
        if self._status_failure is not None:
            raise AudioCaptureError(
                "無法確認音訊輸入裝置狀態；裝置可能已拔除或 Windows driver 已失效。"
                "請先停止擷取、檢查裝置連線，然後重新開始。"
            ) from self._status_failure

    def _cleanup_failed_start(self) -> None:
        self._active = False
        self._stop_event.set()
        worker = self._worker
        if worker is not None:
            worker.join(timeout=self._worker_join_timeout)
        stream = self._stream
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass
            else:
                self._stream = None
        if worker is None or not worker.is_alive():
            self._worker = None
