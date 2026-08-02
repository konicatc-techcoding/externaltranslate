from __future__ import annotations

import importlib
from typing import Any

import numpy as np
import numpy.typing as npt


class AudioConversionError(RuntimeError):
    """Raised when native audio cannot satisfy the downstream PCM contract."""


class Pcm16ChunkConverter:
    """Convert selected float32 input into 16 kHz mono PCM16 100 ms chunks."""

    target_sample_rate = 16000
    chunk_frames = 1600

    def __init__(
        self,
        input_sample_rate: int,
        input_channels: int,
        selected_channel: int | None,
    ) -> None:
        if input_sample_rate <= 0:
            raise ValueError("input_sample_rate 必須大於 0。")
        if input_channels <= 0:
            raise ValueError("input_channels 必須大於 0。")
        if selected_channel is not None and (
            selected_channel < 1 or selected_channel > input_channels
        ):
            raise ValueError("selected_channel 超出輸入 channel 範圍。")

        self._input_sample_rate = input_sample_rate
        self._input_channels = input_channels
        self._selected_channel_index = (
            None if selected_channel is None else selected_channel - 1
        )
        self._buffer = np.empty(0, dtype=np.float32)
        self._finished = False
        self._resampler: Any | None = None
        if input_sample_rate != self.target_sample_rate:
            soxr: Any = importlib.import_module("soxr")
            self._resampler = soxr.ResampleStream(
                input_sample_rate,
                self.target_sample_rate,
                1,
                dtype="float32",
                quality="HQ",
            )

    def process(self, frames: npt.NDArray[np.float32]) -> list[bytes]:
        if self._finished:
            raise AudioConversionError("PCM converter 已結束，不能再接收音訊。")

        values = np.asarray(frames, dtype=np.float32)
        if values.ndim != 2 or values.shape[1] != self._input_channels:
            actual_channels = values.shape[1] if values.ndim == 2 else 0
            raise AudioConversionError(
                f"輸入 frame 的 channel 數量為 {actual_channels}，"
                f"但 stream 設定為 {self._input_channels}。"
            )

        selected = np.ascontiguousarray(
            np.mean(values, axis=1, dtype=np.float32)
            if self._selected_channel_index is None
            else values[:, self._selected_channel_index],
            dtype=np.float32,
        )
        converted = (
            selected
            if self._resampler is None
            else np.asarray(self._resampler.resample_chunk(selected), dtype=np.float32)
        )
        self._append(converted)
        return self._drain_chunks()

    def finish(self) -> list[bytes]:
        if self._finished:
            return []
        self._finished = True
        if self._resampler is not None:
            tail = np.asarray(
                self._resampler.resample_chunk(
                    np.empty(0, dtype=np.float32), last=True
                ),
                dtype=np.float32,
            )
            self._append(tail)
        chunks = self._drain_chunks()
        self._buffer = np.empty(0, dtype=np.float32)
        return chunks

    def _append(self, samples: npt.NDArray[np.float32]) -> None:
        if samples.size:
            self._buffer = np.concatenate((self._buffer, samples))

    def _drain_chunks(self) -> list[bytes]:
        chunks: list[bytes] = []
        while self._buffer.size >= self.chunk_frames:
            samples = self._buffer[: self.chunk_frames]
            self._buffer = self._buffer[self.chunk_frames :]
            clipped = np.clip(samples, -1.0, 1.0 - (1.0 / 32768.0))
            pcm = np.rint(clipped * 32768.0).astype("<i2", copy=False)
            chunks.append(pcm.tobytes())
        return chunks
