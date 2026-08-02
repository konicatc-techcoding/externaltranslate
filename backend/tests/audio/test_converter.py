from __future__ import annotations

import numpy as np
import pytest

from backend.app.audio.converter import AudioConversionError, Pcm16ChunkConverter


def test_converter_selects_channel_and_emits_100ms_little_endian_pcm16() -> None:
    frames = np.zeros((1600, 2), dtype=np.float32)
    frames[:, 1] = 0.5
    converter = Pcm16ChunkConverter(
        input_sample_rate=16000,
        input_channels=2,
        selected_channel=2,
    )

    chunks = converter.process(frames)

    assert len(chunks) == 1
    assert len(chunks[0]) == 3200
    samples = np.frombuffer(chunks[0], dtype="<i2")
    assert samples.shape == (1600,)
    assert np.all(samples == 16384)


def test_converter_resamples_48khz_stream_and_preserves_fixed_chunk_contract() -> None:
    time_axis = np.arange(48000, dtype=np.float32) / 48000.0
    mono = (0.25 * np.sin(2.0 * np.pi * 440.0 * time_axis)).astype(np.float32)
    converter = Pcm16ChunkConverter(
        input_sample_rate=48000,
        input_channels=1,
        selected_channel=1,
    )

    chunks = converter.process(mono.reshape(-1, 1))
    chunks.extend(converter.finish())

    assert len(chunks) == 10
    assert all(len(chunk) == 3200 for chunk in chunks)
    assert any(np.any(np.frombuffer(chunk, dtype="<i2")) for chunk in chunks)


def test_converter_resamples_44100hz_without_losing_fixed_chunk_contract() -> None:
    frames = np.full((44100, 1), 0.125, dtype=np.float32)
    converter = Pcm16ChunkConverter(44100, 1, 1)

    chunks = converter.process(frames)
    chunks.extend(converter.finish())

    assert len(chunks) == 10
    assert all(len(chunk) == 3200 for chunk in chunks)


def test_converter_selects_requested_channel_from_multi_channel_input() -> None:
    frames = np.zeros((1600, 4), dtype=np.float32)
    frames[:, 2] = 0.125
    converter = Pcm16ChunkConverter(16000, 4, 3)

    samples = np.frombuffer(converter.process(frames)[0], dtype="<i2")

    assert np.all(samples == 4096)


def test_converter_downmixes_all_loopback_channels_when_channel_is_none() -> None:
    frames = np.column_stack(
        (
            np.full(1600, 0.25, dtype=np.float32),
            np.full(1600, -0.125, dtype=np.float32),
        )
    )
    converter = Pcm16ChunkConverter(16000, 2, None)

    samples = np.frombuffer(converter.process(frames)[0], dtype="<i2")

    assert np.all(samples == 2048)


def test_converter_saturates_full_scale_samples() -> None:
    frames = np.concatenate(
        [
            np.full(800, -2.0, dtype=np.float32),
            np.full(800, 2.0, dtype=np.float32),
        ]
    ).reshape(-1, 1)
    converter = Pcm16ChunkConverter(16000, 1, 1)

    samples = np.frombuffer(converter.process(frames)[0], dtype="<i2")

    assert samples.min() == -32768
    assert samples.max() == 32767


def test_converter_rejects_frame_shape_that_does_not_match_stream() -> None:
    converter = Pcm16ChunkConverter(48000, 2, 2)

    with pytest.raises(AudioConversionError, match="channel 數量"):
        converter.process(np.zeros((480, 1), dtype=np.float32))
