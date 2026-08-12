from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from backend.app.audio.models import CaptureStats, MeterReading
from backend.app.services.runtime import PipelineRuntime
from backend.app.translation.models import TranslationEvent, TranslationEventKind

_METER = MeterReading(rms=0.1, peak=0.2, rms_dbfs=-20.0, peak_dbfs=-14.0, clipping=False)


class FakeSource:
    """A source that reports whether any PCM ever came out of it."""

    def __init__(self, *, pcm_chunks: int) -> None:
        self._pcm_chunks = pcm_chunks

    @property
    def active(self) -> bool:
        return True

    @property
    def latest_meter(self) -> MeterReading:
        return _METER

    @property
    def stats(self) -> CaptureStats:
        return CaptureStats(
            callback_blocks=self._pcm_chunks,
            callback_errors=0,
            status_events=0,
            processing_errors=0,
            raw_dropped=0,
            pcm_chunks=self._pcm_chunks,
            pcm_dropped=0,
        )

    def start(self) -> None:
        return

    def stop(self) -> None:
        return

    def get_pcm_chunk(self, timeout: float) -> bytes:
        del timeout
        raise TimeoutError


class FakeSession:
    def __init__(self) -> None:
        self.release = asyncio.Event()

    async def send_audio(self, pcm_chunk: bytes) -> None:
        del pcm_chunk

    async def receive_events(self) -> AsyncIterator[TranslationEvent]:
        yield TranslationEvent(
            kind=TranslationEventKind.OUTPUT_TRANSCRIPTION,
            text="你好",
            language_code="zh-Hant",
            finished=False,
        )
        await self.release.wait()

    async def close(self) -> None:
        self.release.set()


class FakeProvider:
    @asynccontextmanager
    async def connect(self) -> AsyncIterator[FakeSession]:
        session = FakeSession()
        try:
            yield session
        finally:
            await session.close()


def _settings(source_kind: str) -> dict[str, Any]:
    audio: dict[str, Any] = {
        "source_kind": source_kind,
        "device_index": 3 if source_kind == "input_device" else None,
        "loopback_endpoint_index": None,
        "channel": 1,
        "raw_queue_capacity": 32,
        "pcm_queue_capacity": 50,
    }
    return {
        "audio": audio,
        "gemini": {
            "model": "gemini-3.5-live-translate-preview",
            "target_language_code": "zh-Hant",
            "echo_target_language": True,
            "session_rotation_seconds": 480,
        },
        "caption": {"max_payload_length": 4096},
    }


def _runtime(*, pcm_chunks: int, source_kind: str = "wasapi_loopback") -> PipelineRuntime:
    return PipelineRuntime(
        _settings(source_kind),
        source_factory=lambda _settings: FakeSource(pcm_chunks=pcm_chunks),
        provider_factory=lambda **_kwargs: FakeProvider(),
        device_lister=lambda: [],
        loopback_lister=lambda: [],
    )


async def _until(predicate: Any, timeout: float = 3.0) -> None:
    async def poll() -> None:
        while not predicate():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(poll(), timeout=timeout)


def test_capture_is_proven_once_pcm_actually_arrives() -> None:
    # Enumerating a device only shows it exists. Producing PCM is the whole
    # path — open, callback, convert, queue — and that is what the environment
    # panel is waiting to be told.
    async def scenario() -> None:
        runtime = _runtime(pcm_chunks=12)
        runtime.set_api_key("secret-api-key-value")
        assert runtime.verified_audio_sources == frozenset()

        await runtime.start()
        await _until(lambda: bool(runtime.snapshot().running))
        await _until(lambda: bool(runtime.verified_audio_sources))
        await runtime.stop()

        # The proof outlives the run: the source is released on stop, and the
        # panel must not go back to "not checked" the moment translation ends.
        assert runtime.verified_audio_sources == frozenset({"wasapi_loopback"})

    asyncio.run(scenario())


def test_a_silent_run_that_produced_no_pcm_proves_nothing() -> None:
    async def scenario() -> None:
        runtime = _runtime(pcm_chunks=0)
        runtime.set_api_key("secret-api-key-value")

        await runtime.start()
        await _until(lambda: runtime.snapshot().running)
        runtime.snapshot()
        await runtime.stop()

        assert runtime.verified_audio_sources == frozenset()

    asyncio.run(scenario())


def test_each_source_kind_is_proven_separately() -> None:
    # Proving the microphone says nothing about system output, and vice versa.
    async def scenario() -> None:
        runtime = _runtime(pcm_chunks=5, source_kind="input_device")
        runtime.set_api_key("secret-api-key-value")

        await runtime.start()
        await _until(lambda: bool(runtime.snapshot().running))
        await _until(lambda: bool(runtime.verified_audio_sources))
        await runtime.stop()

        assert runtime.verified_audio_sources == frozenset({"input_device"})

    asyncio.run(scenario())
