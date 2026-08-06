from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from backend.app.services.translation_pipeline import TranslationPipeline
from backend.app.translation.base import TranslationProviderError
from backend.app.translation.models import TranslationEvent


class QuietAudioSource:
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


class ReceiveFailingSession:
    def __init__(self, *, fail: bool) -> None:
        self.fail = fail
        self.closed = False

    async def send_audio(self, pcm_chunk: bytes) -> None:
        del pcm_chunk

    async def receive_events(self) -> AsyncIterator[TranslationEvent]:
        if self.fail:
            raise TranslationProviderError("safe transient receive", retryable=True)
        await asyncio.Event().wait()
        if False:
            yield TranslationEvent(kind="error")  # type: ignore[arg-type]


class ReconnectingProvider:
    def __init__(self, stop_event: asyncio.Event) -> None:
        self.stop_event = stop_event
        self.sessions: list[ReceiveFailingSession] = []

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[ReceiveFailingSession]:
        session = ReceiveFailingSession(fail=not self.sessions)
        self.sessions.append(session)
        if len(self.sessions) == 2:
            self.stop_event.set()
        try:
            yield session
        finally:
            session.closed = True


def test_retryable_receive_failure_creates_one_replacement() -> None:
    async def scenario() -> None:
        source = QuietAudioSource()
        stop_event = asyncio.Event()
        provider = ReconnectingProvider(stop_event)

        await asyncio.wait_for(
            TranslationPipeline(reconnect_delays=(0.0,)).run(
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
