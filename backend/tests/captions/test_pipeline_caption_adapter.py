from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from backend.app.captions.assembler import CaptionAssembler, CaptionEventSink
from backend.app.captions.models import CaptionStatus
from backend.app.captions.store import CaptionStore
from backend.app.services.translation_pipeline import TranslationPipeline
from backend.app.translation.models import TranslationEvent, TranslationEventKind


class QuietAudioSource:
    started = 0
    stopped = 0

    def start(self) -> None:
        type(self).started += 1

    def stop(self) -> None:
        type(self).stopped += 1

    def get_pcm_chunk(self, timeout: float) -> bytes:
        del timeout
        raise TimeoutError


class SequenceSession:
    def __init__(self, events: list[TranslationEvent], stop: asyncio.Event) -> None:
        self._events = events
        self._stop = stop

    async def send_audio(self, pcm_chunk: bytes) -> None:
        del pcm_chunk

    async def receive_events(self) -> AsyncIterator[TranslationEvent]:
        for event in self._events:
            yield event
        # after the sequence, request the pipeline to stop deterministically
        self._stop.set()
        yield TranslationEvent(kind=TranslationEventKind.SESSION_EXPIRING)


class SequenceProvider:
    def __init__(self, events: list[TranslationEvent], stop: asyncio.Event) -> None:
        self._events = events
        self._stop = stop

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[SequenceSession]:
        yield SequenceSession(self._events, self._stop)


def test_caption_event_sink_commits_assembled_state() -> None:
    async def scenario() -> None:
        assembler = CaptionAssembler()
        store = CaptionStore()
        sink = CaptionEventSink(assembler, store)

        await sink(
            TranslationEvent(
                kind=TranslationEventKind.OUTPUT_TRANSCRIPTION,
                text="你",
                language_code="zh-Hant",
                finished=False,
            )
        )
        await sink(
            TranslationEvent(
                kind=TranslationEventKind.OUTPUT_TRANSCRIPTION,
                text="好",
                language_code="zh-Hant",
                finished=True,
            )
        )

        state = store.snapshot()
        assert state.status is CaptionStatus.FINAL
        assert state.text == "你好"
        assert state.revision == 2

    asyncio.run(scenario())


def test_pipeline_feeds_caption_sink_and_retains_final_across_expiring() -> None:
    async def scenario() -> None:
        assembler = CaptionAssembler()
        store = CaptionStore()
        stop = asyncio.Event()
        events = [
            TranslationEvent(
                kind=TranslationEventKind.OUTPUT_TRANSCRIPTION,
                text="第一句",
                language_code="zh-Hant",
                finished=False,
            ),
            TranslationEvent(
                kind=TranslationEventKind.OUTPUT_TRANSCRIPTION,
                text="。",
                language_code="zh-Hant",
                finished=True,
            ),
        ]
        source = QuietAudioSource()
        sink = CaptionEventSink(assembler, store)

        await asyncio.wait_for(
            TranslationPipeline(reconnect_delays=(0.0,)).run(
                source=source,
                provider=SequenceProvider(events, stop),
                stop_event=stop,
                event_sink=sink,
            ),
            timeout=0.2,
        )

        state = store.snapshot()
        # expiring clears unconfirmed partials but retains the confirmed final
        assert state.status is CaptionStatus.FINAL
        assert state.text == "第一句。"
        assert source.started == 1
        assert source.stopped == 1

    asyncio.run(scenario())


def test_pipeline_caption_sink_clears_partial_on_session_start() -> None:
    async def scenario() -> None:
        assembler = CaptionAssembler()
        store = CaptionStore()
        stop = asyncio.Event()
        events = [
            TranslationEvent(
                kind=TranslationEventKind.OUTPUT_TRANSCRIPTION,
                text="未完成",
                language_code="zh-Hant",
                finished=False,
            ),
            TranslationEvent(kind=TranslationEventKind.SESSION_STARTED),
        ]
        sink = CaptionEventSink(assembler, store)

        await asyncio.wait_for(
            TranslationPipeline(reconnect_delays=(0.0,)).run(
                source=QuietAudioSource(),
                provider=SequenceProvider(events, stop),
                stop_event=stop,
                event_sink=sink,
            ),
            timeout=0.2,
        )

        state = store.snapshot()
        assert state.status is CaptionStatus.IDLE
        assert state.text == ""
        assert state.session_generation == 1

    asyncio.run(scenario())