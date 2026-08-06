from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from backend.app.services.translation_pipeline import TranslationPipeline
from backend.app.translation.models import TranslationEvent, TranslationEventKind


class FakeAudioSource:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1

    def get_pcm_chunk(self, timeout: float) -> bytes:
        del timeout
        raise TimeoutError


class FakeSession:
    def __init__(self, *, expiring: bool = False) -> None:
        self.expiring = expiring
        self.closed = False
        self.release = asyncio.Event()

    async def send_audio(self, pcm_chunk: bytes) -> None:
        del pcm_chunk

    async def receive_events(self) -> AsyncIterator[TranslationEvent]:
        if self.expiring:
            yield TranslationEvent(kind=TranslationEventKind.SESSION_EXPIRING)
        await self.release.wait()

    async def close(self) -> None:
        self.closed = True
        self.release.set()


def test_pipeline_rotates_immediately_after_go_away_event() -> None:
    class GoAwayProvider:
        def __init__(self, stop_event: asyncio.Event) -> None:
            self.stop_event = stop_event
            self.sessions: list[FakeSession] = []

        @asynccontextmanager
        async def connect(self) -> AsyncIterator[FakeSession]:
            session = FakeSession(expiring=not self.sessions)
            self.sessions.append(session)
            if len(self.sessions) == 2:
                self.stop_event.set()
            try:
                yield session
            finally:
                await session.close()

    async def scenario() -> None:
        source = FakeAudioSource()
        stop_event = asyncio.Event()
        provider = GoAwayProvider(stop_event)
        events: list[TranslationEvent] = []

        async def collect(event: TranslationEvent) -> None:
            events.append(event)

        await asyncio.wait_for(
            TranslationPipeline(
                pcm_poll_timeout=0.001,
                session_rotation_seconds=60,
            ).run(
                source=source,
                provider=provider,
                stop_event=stop_event,
                event_sink=collect,
            ),
            timeout=0.1,
        )

        assert len(provider.sessions) == 2
        assert [event.kind for event in events] == [
            TranslationEventKind.SESSION_EXPIRING
        ]
        assert source.started == 1
        assert source.stopped == 1
        assert all(session.closed for session in provider.sessions)

    asyncio.run(scenario())
