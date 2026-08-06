from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from backend.app.services.translation_pipeline import TranslationPipeline
from backend.app.translation.base import TranslationProviderError
from backend.app.translation.models import TranslationEvent


class NeverStartedAudioSource:
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


def test_pipeline_uses_bounded_backoff_for_retryable_connect_failures() -> None:
    class FailingProvider:
        def __init__(self) -> None:
            self.attempts = 0

        @asynccontextmanager
        async def connect(self) -> AsyncIterator[object]:
            self.attempts += 1
            raise TranslationProviderError("暫時性connect失敗", retryable=True)
            yield object()

    async def scenario() -> None:
        source = NeverStartedAudioSource()
        provider = FailingProvider()
        delays: list[float] = []

        async def wait_for_stop(_stop_event: asyncio.Event, delay: float) -> bool:
            delays.append(delay)
            return len(delays) == 6

        async def collect(event: TranslationEvent) -> None:
            del event

        await TranslationPipeline(
            reconnect_delays=(0.5, 1.0, 2.0, 4.0, 5.0),
            reconnect_waiter=wait_for_stop,
        ).run(
            source=source,
            provider=provider,
            stop_event=asyncio.Event(),
            event_sink=collect,
        )

        assert delays == [0.5, 1.0, 2.0, 4.0, 5.0, 5.0]
        assert provider.attempts == 6
        assert source.started == 1
        assert source.stopped == 1

    asyncio.run(scenario())


def test_audio_source_runs_while_initial_connect_is_retrying() -> None:
    async def scenario() -> None:
        source = NeverStartedAudioSource()
        observed_source_states: list[tuple[int, int]] = []

        class FailingProvider:
            @asynccontextmanager
            async def connect(self) -> AsyncIterator[object]:
                observed_source_states.append((source.started, source.stopped))
                raise TranslationProviderError("暫時性connect失敗", retryable=True)
                yield object()

        async def stop_after_first_delay(
            _stop_event: asyncio.Event, _delay: float
        ) -> bool:
            assert source.started == 1
            assert source.stopped == 0
            return True

        async def collect(event: TranslationEvent) -> None:
            del event

        await TranslationPipeline(reconnect_waiter=stop_after_first_delay).run(
            source=source,
            provider=FailingProvider(),
            stop_event=asyncio.Event(),
            event_sink=collect,
        )

        assert observed_source_states == [(1, 0)]
        assert source.started == 1
        assert source.stopped == 1

    asyncio.run(scenario())
