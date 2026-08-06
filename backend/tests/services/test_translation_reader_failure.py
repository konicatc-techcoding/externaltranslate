from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from backend.app.services.translation_pipeline import (
    TranslationPipeline,
    TranslationPipelineError,
)
from backend.app.translation.base import TranslationProviderError


class FailingAudioSource:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0
        self.failed = threading.Event()

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1

    def get_pcm_chunk(self, timeout: float) -> bytes:
        del timeout
        self.failed.set()
        raise RuntimeError("secret-reader-detail")


class RetryableProvider:
    def __init__(self) -> None:
        self.attempts = 0

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[object]:
        self.attempts += 1
        raise TranslationProviderError("safe transient connect", retryable=True)
        yield object()


def test_reader_failure_stops_connect_retries_without_raw_detail() -> None:
    async def scenario() -> None:
        source = FailingAudioSource()
        provider = RetryableProvider()

        async def yield_once(_stop_event: asyncio.Event, _delay: float) -> bool:
            await asyncio.to_thread(source.failed.wait, 0.1)
            await asyncio.sleep(0)
            return False

        with pytest.raises(TranslationPipelineError) as caught:
            await asyncio.wait_for(
                TranslationPipeline(
                    reconnect_delays=(0.0,), reconnect_waiter=yield_once
                ).run(
                    source=source,
                    provider=provider,
                    stop_event=asyncio.Event(),
                    event_sink=lambda _event: asyncio.sleep(0),
                ),
                timeout=0.2,
            )

        assert "secret" not in str(caught.value).lower()
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None
        assert provider.attempts <= 2
        assert source.started == 1
        assert source.stopped == 1

    asyncio.run(scenario())
