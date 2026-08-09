from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from google.genai import types

from backend.app.captions.assembler import CaptionAssembler, CaptionEventSink
from backend.app.captions.store import CaptionStore
from backend.app.services.translation_pipeline import TranslationPipeline
from backend.app.translation.base import TranslationProviderError
from backend.app.translation.gemini_live import GeminiLiveSession
from backend.app.translation.models import TranslationEvent, TranslationEventKind


class FakeSdkSession:
    def __init__(self, messages: list[types.LiveServerMessage]) -> None:
        self.messages = messages

    async def send_realtime_input(self, **kwargs: Any) -> None:
        del kwargs

    def receive(self) -> AsyncIterator[types.LiveServerMessage]:
        # Each receive() call drains the queue: a replaying fake would loop
        # forever inside the adapter's multi-turn receive loop.
        pending, self.messages = self.messages, []

        async def responses() -> AsyncIterator[types.LiveServerMessage]:
            for message in pending:
                yield message

        return responses()


def _output_message(text: str) -> types.LiveServerMessage:
    return types.LiveServerMessage(
        server_content=types.LiveServerContent(
            output_transcription=types.Transcription(
                text=text, language_code="zh-Hant", finished=False
            )
        )
    )


def test_receive_events_starts_with_session_started() -> None:
    async def scenario() -> None:
        session = GeminiLiveSession(FakeSdkSession([_output_message("你好")]))
        events: list[TranslationEvent] = []
        with pytest.raises(TranslationProviderError):
            async for event in session.receive_events():
                events.append(event)

        assert events[0].kind is TranslationEventKind.SESSION_STARTED
        assert events[1].kind is TranslationEventKind.OUTPUT_TRANSCRIPTION

    asyncio.run(scenario())


def test_session_started_is_emitted_once_per_session() -> None:
    async def scenario() -> None:
        session = GeminiLiveSession(
            FakeSdkSession([_output_message("一"), _output_message("二")])
        )
        events: list[TranslationEvent] = []
        with pytest.raises(TranslationProviderError):
            async for event in session.receive_events():
                events.append(event)

        started = [
            event
            for event in events
            if event.kind is TranslationEventKind.SESSION_STARTED
        ]
        assert len(started) == 1

    asyncio.run(scenario())


class QuietSource:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0

    @property
    def active(self) -> bool:
        return self.started > self.stopped

    @property
    def latest_meter(self) -> Any:
        return None

    @property
    def stats(self) -> Any:
        return None

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1

    def get_pcm_chunk(self, timeout: float) -> bytes:
        del timeout
        raise TimeoutError


class ScriptedSession:
    def __init__(self, events: list[TranslationEvent]) -> None:
        self._events = events
        self.release = asyncio.Event()

    async def send_audio(self, pcm_chunk: bytes) -> None:
        del pcm_chunk

    async def receive_events(self) -> AsyncIterator[TranslationEvent]:
        for event in self._events:
            yield event
        await self.release.wait()

    async def close(self) -> None:
        self.release.set()


def test_pipeline_emits_session_stopped_when_a_session_ends() -> None:
    async def scenario() -> None:
        stop = asyncio.Event()

        class RotatingProvider:
            def __init__(self) -> None:
                self.sessions = 0

            @asynccontextmanager
            async def connect(self) -> AsyncIterator[ScriptedSession]:
                self.sessions += 1
                events = [
                    TranslationEvent(kind=TranslationEventKind.SESSION_STARTED),
                ]
                if self.sessions == 1:
                    events.append(
                        TranslationEvent(kind=TranslationEventKind.SESSION_EXPIRING)
                    )
                else:
                    stop.set()
                session = ScriptedSession(events)
                try:
                    yield session
                finally:
                    await session.close()

        seen: list[TranslationEventKind] = []

        async def collect(event: TranslationEvent) -> None:
            seen.append(event.kind)

        await asyncio.wait_for(
            TranslationPipeline(pcm_poll_timeout=0.001, session_rotation_seconds=60).run(
                source=QuietSource(),
                provider=RotatingProvider(),
                stop_event=stop,
                event_sink=collect,
            ),
            timeout=1.0,
        )

        assert seen.count(TranslationEventKind.SESSION_STARTED) == 2
        assert seen.count(TranslationEventKind.SESSION_STOPPED) == 2
        # each session must be closed before the next one opens
        assert seen[-1] is TranslationEventKind.SESSION_STOPPED

    asyncio.run(scenario())


def test_caption_session_generation_advances_across_rotation() -> None:
    async def scenario() -> None:
        stop = asyncio.Event()

        class RotatingProvider:
            def __init__(self) -> None:
                self.sessions = 0

            @asynccontextmanager
            async def connect(self) -> AsyncIterator[ScriptedSession]:
                self.sessions += 1
                events = [
                    TranslationEvent(kind=TranslationEventKind.SESSION_STARTED),
                    TranslationEvent(
                        kind=TranslationEventKind.OUTPUT_TRANSCRIPTION,
                        text=f"第{self.sessions}段",
                        language_code="zh-Hant",
                        finished=True,
                    ),
                ]
                if self.sessions == 1:
                    events.append(
                        TranslationEvent(kind=TranslationEventKind.SESSION_EXPIRING)
                    )
                else:
                    stop.set()
                session = ScriptedSession(events)
                try:
                    yield session
                finally:
                    await session.close()

        store = CaptionStore()
        sink = CaptionEventSink(CaptionAssembler(), store)

        await asyncio.wait_for(
            TranslationPipeline(pcm_poll_timeout=0.001, session_rotation_seconds=60).run(
                source=QuietSource(),
                provider=RotatingProvider(),
                stop_event=stop,
                event_sink=sink,
            ),
            timeout=1.0,
        )

        assert store.snapshot().session_generation >= 2

    asyncio.run(scenario())
