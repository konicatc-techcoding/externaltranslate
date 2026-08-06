from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from backend.app.services.translation_pipeline import (
    TranslationPipeline,
    TranslationPipelineError,
)
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


def test_pipeline_does_not_retry_permanent_connect_error() -> None:
    class PermanentFailingProvider:
        def __init__(self) -> None:
            self.attempts = 0

        @asynccontextmanager
        async def connect(self) -> AsyncIterator[object]:
            self.attempts += 1
            raise TranslationProviderError("safe permanent error", retryable=False)
            yield object()

    async def scenario() -> None:
        source = FakeAudioSource()
        provider = PermanentFailingProvider()

        async def unexpected_waiter(
            _stop_event: asyncio.Event, _delay: float
        ) -> bool:
            raise AssertionError("permanent error不可進入backoff")

        async def collect(event: TranslationEvent) -> None:
            del event

        try:
            await TranslationPipeline(reconnect_waiter=unexpected_waiter).run(
                source=source,
                provider=provider,
                stop_event=asyncio.Event(),
                event_sink=collect,
            )
        except TranslationPipelineError as exc:
            assert "safe permanent error" not in str(exc)
            assert exc.__cause__ is None
            assert exc.__context__ is None
        else:
            raise AssertionError("permanent provider error必須停止pipeline")

        assert provider.attempts == 1
        assert source.started == 1
        assert source.stopped == 1

    asyncio.run(scenario())
