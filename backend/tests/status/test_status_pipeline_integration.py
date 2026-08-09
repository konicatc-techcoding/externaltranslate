from __future__ import annotations

import asyncio
import itertools
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from backend.app.services.translation_pipeline import (
    TranslationPipeline,
    TranslationPipelineError,
)
from backend.app.status.models import Component, ComponentState, ComponentStatus
from backend.app.status.publisher import StatusPublisher
from backend.app.status.store import StatusStore
from backend.app.translation.base import TranslationProviderError
from backend.app.translation.models import TranslationEvent, TranslationEventKind


class FakeAudioSource:
    def __init__(self, *, fail_start: bool = False) -> None:
        self.started = 0
        self.stopped = 0
        self._fail_start = fail_start

    def start(self) -> None:
        self.started += 1
        if self._fail_start:
            raise RuntimeError("device gone")

    def stop(self) -> None:
        self.stopped += 1

    def get_pcm_chunk(self, timeout: float) -> bytes:
        del timeout
        raise TimeoutError


class FakeSession:
    def __init__(self, *, expiring: bool = False) -> None:
        self.expiring = expiring
        self.release = asyncio.Event()

    async def send_audio(self, pcm_chunk: bytes) -> None:
        del pcm_chunk

    async def receive_events(self) -> AsyncIterator[TranslationEvent]:
        if self.expiring:
            yield TranslationEvent(kind=TranslationEventKind.SESSION_EXPIRING)
        await self.release.wait()

    async def close(self) -> None:
        self.release.set()


def _publisher() -> tuple[StatusPublisher, StatusStore, list[ComponentStatus]]:
    store = StatusStore()
    seen: list[ComponentStatus] = []
    clock = itertools.count(1.0, 1.0)
    publisher = StatusPublisher(store, now=lambda: next(clock), sink=seen.append)
    return publisher, store, seen


def _transitions(seen: list[ComponentStatus]) -> list[tuple[str, str]]:
    return [(status.component.value, status.state.value) for status in seen]


def _details(
    seen: list[ComponentStatus], component: Component, state: ComponentState
) -> list[str | None]:
    return [
        status.detail
        for status in seen
        if status.component is component and status.state is state
    ]


async def _collect(event: TranslationEvent) -> None:
    del event


def test_pipeline_publishes_audio_and_session_lifecycle() -> None:
    async def scenario() -> None:
        publisher, store, seen = _publisher()
        source = FakeAudioSource()
        stop_event = asyncio.Event()

        class StoppingProvider:
            @asynccontextmanager
            async def connect(self) -> AsyncIterator[FakeSession]:
                session = FakeSession()
                stop_event.set()
                try:
                    yield session
                finally:
                    await session.close()

        await asyncio.wait_for(
            TranslationPipeline(
                pcm_poll_timeout=0.001, status_publisher=publisher
            ).run(
                source=source,
                provider=StoppingProvider(),
                stop_event=stop_event,
                event_sink=_collect,
            ),
            timeout=1.0,
        )

        assert _transitions(seen) == [
            ("audio_source", "starting"),
            ("audio_source", "running"),
            ("gemini_provider", "connecting"),
            ("gemini_provider", "connected"),
            ("gemini_session", "active"),
            ("gemini_session", "stopped"),
            ("gemini_provider", "stopped"),
            ("audio_source", "stopping"),
            ("audio_source", "stopped"),
        ]
        assert store.last(Component.AUDIO_SOURCE).state is ComponentState.STOPPED
        active = _details(seen, Component.GEMINI_SESSION, ComponentState.ACTIVE)
        assert active and "generation=1" in (active[0] or "")

    asyncio.run(scenario())


def test_pipeline_publishes_goaway_rotation_with_new_generation() -> None:
    async def scenario() -> None:
        publisher, _store, seen = _publisher()
        stop_event = asyncio.Event()

        class GoAwayProvider:
            def __init__(self) -> None:
                self.sessions: list[FakeSession] = []

            @asynccontextmanager
            async def connect(self) -> AsyncIterator[FakeSession]:
                session = FakeSession(expiring=not self.sessions)
                self.sessions.append(session)
                if len(self.sessions) == 2:
                    stop_event.set()
                try:
                    yield session
                finally:
                    await session.close()

        await asyncio.wait_for(
            TranslationPipeline(
                pcm_poll_timeout=0.001,
                session_rotation_seconds=60,
                status_publisher=publisher,
            ).run(
                source=FakeAudioSource(),
                provider=GoAwayProvider(),
                stop_event=stop_event,
                event_sink=_collect,
            ),
            timeout=1.0,
        )

        rotating = _details(seen, Component.GEMINI_SESSION, ComponentState.ROTATING)
        assert rotating == ["generation=1 reason=goaway"]
        active = _details(seen, Component.GEMINI_SESSION, ComponentState.ACTIVE)
        assert [detail and "generation=1" in detail for detail in active][0] is True
        assert any("generation=2" in (detail or "") for detail in active)

    asyncio.run(scenario())


def test_pipeline_publishes_timer_rotation() -> None:
    async def scenario() -> None:
        publisher, _store, seen = _publisher()
        stop_event = asyncio.Event()

        class RotatingProvider:
            def __init__(self) -> None:
                self.sessions: list[FakeSession] = []

            @asynccontextmanager
            async def connect(self) -> AsyncIterator[FakeSession]:
                session = FakeSession()
                self.sessions.append(session)
                if len(self.sessions) == 2:
                    stop_event.set()
                try:
                    yield session
                finally:
                    await session.close()

        await asyncio.wait_for(
            TranslationPipeline(
                pcm_poll_timeout=0.001,
                session_rotation_seconds=0.01,
                status_publisher=publisher,
            ).run(
                source=FakeAudioSource(),
                provider=RotatingProvider(),
                stop_event=stop_event,
                event_sink=_collect,
            ),
            timeout=1.0,
        )

        rotating = _details(seen, Component.GEMINI_SESSION, ComponentState.ROTATING)
        assert rotating and rotating[0] == "generation=1 reason=timer"

    asyncio.run(scenario())


def test_pipeline_publishes_backoff_attempt_and_delay() -> None:
    async def scenario() -> None:
        publisher, _store, seen = _publisher()

        class FailingProvider:
            @asynccontextmanager
            async def connect(self) -> AsyncIterator[object]:
                raise TranslationProviderError("暫時性connect失敗", retryable=True)
                yield object()

        attempts = 0

        async def wait_for_stop(_stop_event: asyncio.Event, delay: float) -> bool:
            nonlocal attempts
            del delay
            attempts += 1
            return attempts == 2

        await TranslationPipeline(
            reconnect_delays=(0.5, 1.0),
            reconnect_waiter=wait_for_stop,
            status_publisher=publisher,
        ).run(
            source=FakeAudioSource(),
            provider=FailingProvider(),
            stop_event=asyncio.Event(),
            event_sink=_collect,
        )

        backoff = _details(seen, Component.GEMINI_PROVIDER, ComponentState.BACKOFF)
        assert backoff == [
            "reason=error attempt=1 delay_seconds=0.5",
            "reason=error attempt=2 delay_seconds=1.0",
        ]

    asyncio.run(scenario())


def test_pipeline_publishes_fail_closed_and_keeps_it_visible() -> None:
    async def scenario() -> None:
        publisher, store, seen = _publisher()

        class PermanentProvider:
            @asynccontextmanager
            async def connect(self) -> AsyncIterator[object]:
                raise TranslationProviderError("API權限不足", retryable=False)
                yield object()

        with pytest.raises(TranslationPipelineError):
            await TranslationPipeline(status_publisher=publisher).run(
                source=FakeAudioSource(),
                provider=PermanentProvider(),
                stop_event=asyncio.Event(),
                event_sink=_collect,
            )

        assert ("gemini_provider", "fail_closed") in _transitions(seen)
        # fail_closed must survive teardown, otherwise the UI would show a
        # harmless "stopped" for an unrecoverable credential problem.
        assert (
            store.last(Component.GEMINI_PROVIDER).state is ComponentState.FAIL_CLOSED
        )
        assert ("gemini_provider", "stopped") not in _transitions(seen)

    asyncio.run(scenario())


def test_pipeline_publishes_audio_error_and_skips_provider() -> None:
    async def scenario() -> None:
        publisher, store, seen = _publisher()

        class UnusedProvider:
            @asynccontextmanager
            async def connect(self) -> AsyncIterator[object]:
                raise AssertionError("provider must not be used")
                yield object()

        with pytest.raises(TranslationPipelineError):
            await TranslationPipeline(status_publisher=publisher).run(
                source=FakeAudioSource(fail_start=True),
                provider=UnusedProvider(),
                stop_event=asyncio.Event(),
                event_sink=_collect,
            )

        assert ("audio_source", "error") in _transitions(seen)
        assert store.last(Component.GEMINI_PROVIDER).state is ComponentState.IDLE

    asyncio.run(scenario())


def test_status_publish_failure_does_not_break_the_pipeline() -> None:
    async def scenario() -> None:
        class BrokenPublisher(StatusPublisher):
            def publish(
                self,
                component: Component,
                state: ComponentState,
                **fields: object,
            ) -> ComponentStatus:
                raise RuntimeError("status backend down")

        source = FakeAudioSource()
        stop_event = asyncio.Event()

        class StoppingProvider:
            @asynccontextmanager
            async def connect(self) -> AsyncIterator[FakeSession]:
                session = FakeSession()
                stop_event.set()
                try:
                    yield session
                finally:
                    await session.close()

        await asyncio.wait_for(
            TranslationPipeline(
                pcm_poll_timeout=0.001,
                status_publisher=BrokenPublisher(StatusStore()),
            ).run(
                source=source,
                provider=StoppingProvider(),
                stop_event=stop_event,
                event_sink=_collect,
            ),
            timeout=1.0,
        )

        assert source.started == 1
        assert source.stopped == 1

    asyncio.run(scenario())
