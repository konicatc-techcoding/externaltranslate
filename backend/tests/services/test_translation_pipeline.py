from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from backend.app.services.translation_pipeline import (
    TranslationPipeline,
    TranslationPipelineError,
)
from backend.app.translation.models import TranslationEvent, TranslationEventKind


class FakeAudioSource:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0
        self._chunks = [b"\x01\x00" * 1600]

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1

    def get_pcm_chunk(self, timeout: float) -> bytes:
        del timeout
        if self._chunks:
            return self._chunks.pop(0)
        raise TimeoutError


class FakeTranslationSession:
    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.closed = False
        self.sent_event = asyncio.Event()
        self.release = asyncio.Event()

    async def send_audio(self, pcm_chunk: bytes) -> None:
        self.sent.append(pcm_chunk)
        self.sent_event.set()

    async def receive_events(self) -> AsyncIterator[TranslationEvent]:
        await self.sent_event.wait()
        yield TranslationEvent(
            kind=TranslationEventKind.OUTPUT_TRANSCRIPTION,
            text="你好",
            language_code="zh-Hant",
            finished=False,
        )
        await self.release.wait()

    async def close(self) -> None:
        self.closed = True
        self.release.set()


class FakeTranslationProvider:
    def __init__(self, session: FakeTranslationSession) -> None:
        self.session = session

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[FakeTranslationSession]:
        try:
            yield self.session
        finally:
            await self.session.close()


def test_pipeline_streams_pcm_and_closes_source_and_session() -> None:
    async def scenario() -> None:
        source = FakeAudioSource()
        session = FakeTranslationSession()
        stop_event = asyncio.Event()
        events: list[TranslationEvent] = []

        async def collect(event: TranslationEvent) -> None:
            events.append(event)
            stop_event.set()

        pipeline = TranslationPipeline(pcm_poll_timeout=0.01)
        await pipeline.run(
            source=source,
            provider=FakeTranslationProvider(session),
            stop_event=stop_event,
            event_sink=collect,
        )

        assert source.started == 1
        assert source.stopped == 1
        assert session.sent == [b"\x01\x00" * 1600]
        assert session.closed is True
        assert [event.text for event in events] == ["你好"]

    asyncio.run(scenario())


def test_pipeline_maps_sender_failure_and_still_closes_resources() -> None:
    class FailingSession(FakeTranslationSession):
        async def send_audio(self, pcm_chunk: bytes) -> None:
            del pcm_chunk
            raise RuntimeError("secret-api-key-value")

        async def receive_events(self) -> AsyncIterator[TranslationEvent]:
            await self.release.wait()
            if False:
                yield TranslationEvent(kind=TranslationEventKind.SESSION_STOPPED)

    async def scenario() -> None:
        source = FakeAudioSource()
        session = FailingSession()

        async def collect(event: TranslationEvent) -> None:
            del event

        with pytest.raises(TranslationPipelineError) as caught:
            await TranslationPipeline(pcm_poll_timeout=0.01).run(
                source=source,
                provider=FakeTranslationProvider(session),
                stop_event=asyncio.Event(),
                event_sink=collect,
            )

        assert "secret-api-key-value" not in str(caught.value)
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None
        assert source.stopped == 1
        assert session.closed is True

    asyncio.run(scenario())


def test_pipeline_maps_source_stop_failure_without_leaking_raw_message() -> None:
    class StopFailingSource(FakeAudioSource):
        def stop(self) -> None:
            self.stopped += 1
            raise RuntimeError("secret-stop-detail")

    async def scenario() -> None:
        source = StopFailingSource()
        session = FakeTranslationSession()
        stop_event = asyncio.Event()

        async def collect(event: TranslationEvent) -> None:
            del event
            stop_event.set()

        with pytest.raises(TranslationPipelineError) as caught:
            await TranslationPipeline(pcm_poll_timeout=0.01).run(
                source=source,
                provider=FakeTranslationProvider(session),
                stop_event=stop_event,
                event_sink=collect,
            )

        assert "secret-stop-detail" not in str(caught.value)
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None
        assert source.stopped == 1
        assert session.closed is True

    asyncio.run(scenario())


def test_pipeline_maps_source_start_failure_and_retries_cleanup() -> None:
    class StartFailingSource(FakeAudioSource):
        def start(self) -> None:
            self.started += 1
            raise RuntimeError("secret-start-detail")

    async def scenario() -> None:
        source = StartFailingSource()
        session = FakeTranslationSession()

        async def collect(event: TranslationEvent) -> None:
            del event

        with pytest.raises(TranslationPipelineError) as caught:
            await TranslationPipeline(pcm_poll_timeout=0.01).run(
                source=source,
                provider=FakeTranslationProvider(session),
                stop_event=asyncio.Event(),
                event_sink=collect,
            )

        assert "secret-start-detail" not in str(caught.value)
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None
        assert source.started == 1
        assert source.stopped == 1
        assert session.closed is False

    asyncio.run(scenario())


def test_pipeline_cancellation_closes_all_owned_resources() -> None:
    async def scenario() -> None:
        source = FakeAudioSource()
        session = FakeTranslationSession()

        async def collect(event: TranslationEvent) -> None:
            del event

        task = asyncio.create_task(
            TranslationPipeline(pcm_poll_timeout=0.01).run(
                source=source,
                provider=FakeTranslationProvider(session),
                stop_event=asyncio.Event(),
                event_sink=collect,
            )
        )
        await session.sent_event.wait()
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert source.stopped == 1
        assert session.closed is True
        active_names = {
            pending.get_name()
            for pending in asyncio.all_tasks()
            if pending is not asyncio.current_task() and not pending.done()
        }
        assert "translation-audio-sender" not in active_names
        assert "translation-event-receiver" not in active_names
        assert "translation-stop-waiter" not in active_names
        assert "translation-session-rotator" not in active_names
        assert "translation-pcm-reader" not in active_names

    asyncio.run(scenario())


def test_pipeline_worker_failure_wins_over_simultaneous_stop_signal() -> None:
    class StopAndFailSession(FakeTranslationSession):
        def __init__(self, stop_event: asyncio.Event) -> None:
            super().__init__()
            self._stop_event = stop_event

        async def send_audio(self, pcm_chunk: bytes) -> None:
            del pcm_chunk
            self._stop_event.set()
            raise RuntimeError("simultaneous-send-failure")

        async def receive_events(self) -> AsyncIterator[TranslationEvent]:
            await self.release.wait()
            if False:
                yield TranslationEvent(kind=TranslationEventKind.SESSION_STOPPED)

    async def scenario() -> None:
        stop_event = asyncio.Event()
        source = FakeAudioSource()
        session = StopAndFailSession(stop_event)

        async def collect(event: TranslationEvent) -> None:
            del event

        with pytest.raises(TranslationPipelineError) as caught:
            await TranslationPipeline(pcm_poll_timeout=0.01).run(
                source=source,
                provider=FakeTranslationProvider(session),
                stop_event=stop_event,
                event_sink=collect,
            )

        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None
        assert source.stopped == 1
        assert session.closed is True

    asyncio.run(scenario())
