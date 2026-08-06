from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from backend.app.services.translation_pipeline import TranslationPipeline
from backend.app.translation.base import TranslationProviderError
from backend.app.translation.models import TranslationEvent


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


class FakeTranslationSession:
    def __init__(self) -> None:
        self.closed = False
        self.release = asyncio.Event()

    async def send_audio(self, pcm_chunk: bytes) -> None:
        del pcm_chunk

    async def receive_events(self) -> AsyncIterator[TranslationEvent]:
        await self.release.wait()
        if False:
            yield TranslationEvent(kind="session_stopped")

    async def close(self) -> None:
        self.closed = True
        self.release.set()


def test_pipeline_rotates_session_without_restarting_audio_source() -> None:
    class RotatingProvider:
        def __init__(self, stop_event: asyncio.Event) -> None:
            self.stop_event = stop_event
            self.sessions: list[FakeTranslationSession] = []

        @asynccontextmanager
        async def connect(self) -> AsyncIterator[FakeTranslationSession]:
            session = FakeTranslationSession()
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
        provider = RotatingProvider(stop_event)

        async def collect(event: TranslationEvent) -> None:
            del event

        await TranslationPipeline(
            pcm_poll_timeout=0.001,
            session_rotation_seconds=0.01,
        ).run(
            source=source,
            provider=provider,
            stop_event=stop_event,
            event_sink=collect,
        )

        assert source.started == 1
        assert source.stopped == 1
        assert len(provider.sessions) == 2
        assert all(session.closed for session in provider.sessions)

    asyncio.run(scenario())


def test_pipeline_reconnects_after_retryable_session_send_error() -> None:
    class ChunkAudioSource(FakeAudioSource):
        def get_pcm_chunk(self, timeout: float) -> bytes:
            del timeout
            return b"\x00\x00" * 1600

    class FailingSession(FakeTranslationSession):
        async def send_audio(self, pcm_chunk: bytes) -> None:
            del pcm_chunk
            raise TranslationProviderError("暫時性send失敗", retryable=True)

    class ReconnectingProvider:
        def __init__(self, stop_event: asyncio.Event) -> None:
            self.stop_event = stop_event
            self.sessions: list[FakeTranslationSession] = []

        @asynccontextmanager
        async def connect(self) -> AsyncIterator[FakeTranslationSession]:
            session: FakeTranslationSession
            if not self.sessions:
                session = FailingSession()
            else:
                session = FakeTranslationSession()
                self.stop_event.set()
            self.sessions.append(session)
            try:
                yield session
            finally:
                await session.close()

    async def scenario() -> None:
        source = ChunkAudioSource()
        stop_event = asyncio.Event()
        provider = ReconnectingProvider(stop_event)

        async def collect(event: TranslationEvent) -> None:
            del event

        await TranslationPipeline(
            pcm_poll_timeout=0.001,
            session_rotation_seconds=60,
            reconnect_delays=(0.0,),
        ).run(
            source=source,
            provider=provider,
            stop_event=stop_event,
            event_sink=collect,
        )

        assert len(provider.sessions) == 2
        assert source.started == 1
        assert source.stopped == 1
        assert all(session.closed for session in provider.sessions)

    asyncio.run(scenario())


def test_timer_and_send_error_race_create_only_one_replacement() -> None:
    class ChunkAudioSource(FakeAudioSource):
        def get_pcm_chunk(self, timeout: float) -> bytes:
            del timeout
            return b"\x00\x00" * 1600

    class TimedFailingSession(FakeTranslationSession):
        async def send_audio(self, pcm_chunk: bytes) -> None:
            del pcm_chunk
            await asyncio.sleep(0.01)
            raise TranslationProviderError("暫時性send失敗", retryable=True)

    class RacingProvider:
        def __init__(self, stop_event: asyncio.Event) -> None:
            self.stop_event = stop_event
            self.sessions: list[FakeTranslationSession] = []

        @asynccontextmanager
        async def connect(self) -> AsyncIterator[FakeTranslationSession]:
            session: FakeTranslationSession
            if not self.sessions:
                session = TimedFailingSession()
            else:
                session = FakeTranslationSession()
                self.stop_event.set()
            self.sessions.append(session)
            try:
                yield session
            finally:
                await session.close()

    async def scenario() -> None:
        source = ChunkAudioSource()
        stop_event = asyncio.Event()
        provider = RacingProvider(stop_event)

        await asyncio.wait_for(
            TranslationPipeline(
                pcm_poll_timeout=0.001,
                session_rotation_seconds=0.01,
                reconnect_delays=(0.0,),
            ).run(
                source=source,
                provider=provider,
                stop_event=stop_event,
                event_sink=lambda _event: asyncio.sleep(0),
            ),
            timeout=0.2,
        )

        assert len(provider.sessions) == 2
        assert all(session.closed for session in provider.sessions)
        assert source.started == 1
        assert source.stopped == 1

    asyncio.run(scenario())
