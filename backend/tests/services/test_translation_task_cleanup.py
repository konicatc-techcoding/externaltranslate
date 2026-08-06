from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from backend.app.services.translation_pipeline import (
    TranslationPipeline,
    TranslationPipelineError,
)
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


class CleanupFailingSession:
    async def send_audio(self, pcm_chunk: bytes) -> None:
        del pcm_chunk

    async def receive_events(self) -> AsyncIterator[TranslationEvent]:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise RuntimeError("secret-receiver-cleanup-detail") from None
        if False:
            yield TranslationEvent(kind="error")  # type: ignore[arg-type]


class CountingProvider:
    def __init__(self) -> None:
        self.connections = 0

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[CleanupFailingSession]:
        self.connections += 1
        yield CleanupFailingSession()


def test_session_task_cleanup_failure_is_visible_and_blocks_replacement() -> None:
    async def scenario() -> None:
        source = QuietAudioSource()
        provider = CountingProvider()

        with pytest.raises(TranslationPipelineError) as caught:
            await asyncio.wait_for(
                TranslationPipeline(session_rotation_seconds=0.01).run(
                    source=source,
                    provider=provider,
                    stop_event=asyncio.Event(),
                    event_sink=lambda _event: asyncio.sleep(0),
                ),
                timeout=0.1,
            )

        assert "cleanup" in str(caught.value).lower()
        assert "secret" not in str(caught.value).lower()
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None
        assert provider.connections == 1
        assert source.started == 1
        assert source.stopped == 1

    asyncio.run(scenario())
