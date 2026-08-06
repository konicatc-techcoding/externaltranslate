from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from backend.app.services.translation_pipeline import TranslationPipeline
from backend.app.translation.models import TranslationEvent


class BlockingAudioSource:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.release = threading.Event()
        self.started = 0
        self.stopped = 0
        self.active_reads = 0
        self.max_active_reads = 0

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1
        self.release.set()

    def get_pcm_chunk(self, timeout: float) -> bytes:
        del timeout
        with self._lock:
            self.active_reads += 1
            self.max_active_reads = max(self.max_active_reads, self.active_reads)
        try:
            self.release.wait(timeout=1.0)
            raise TimeoutError
        finally:
            with self._lock:
                self.active_reads -= 1


class WaitingSession:
    async def send_audio(self, pcm_chunk: bytes) -> None:
        del pcm_chunk

    async def receive_events(self) -> AsyncIterator[TranslationEvent]:
        await asyncio.Event().wait()
        if False:
            yield TranslationEvent(kind="error")  # type: ignore[arg-type]


class RotatingProvider:
    def __init__(self) -> None:
        self.connections = 0

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[WaitingSession]:
        self.connections += 1
        yield WaitingSession()


def test_rotation_never_starts_a_second_pcm_reader() -> None:
    async def scenario() -> None:
        source = BlockingAudioSource()
        provider = RotatingProvider()
        stop_event = asyncio.Event()

        async def collect(event: TranslationEvent) -> None:
            del event

        task = asyncio.create_task(
            TranslationPipeline(
                pcm_poll_timeout=0.01,
                session_rotation_seconds=0.01,
                reconnect_delays=(0.0,),
            ).run(
                source=source,
                provider=provider,
                stop_event=stop_event,
                event_sink=collect,
            )
        )

        await asyncio.sleep(0.08)
        observed_max = source.max_active_reads
        stop_event.set()
        source.release.set()
        await asyncio.wait_for(task, timeout=1.0)

        assert provider.connections >= 2
        assert observed_max == 1
        assert source.active_reads == 0
        assert source.started == 1
        assert source.stopped == 1

    asyncio.run(scenario())
