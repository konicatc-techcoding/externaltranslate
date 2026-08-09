from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any

import pytest

from backend.app.audio.models import MeterReading
from backend.app.captions.models import CaptionStatus
from backend.app.services.runtime import (
    PipelineRuntime,
    RuntimeConflictError,
    RuntimeCredentialError,
)
from backend.app.status.models import Component, ComponentState
from backend.app.translation.models import TranslationEvent, TranslationEventKind

_SETTINGS: dict[str, Any] = {
    "audio": {
        "source_kind": "wasapi_loopback",
        "device_index": None,
        "loopback_endpoint_index": None,
        "channel": 1,
        "raw_queue_capacity": 32,
        "pcm_queue_capacity": 50,
    },
    "gemini": {
        "model": "gemini-3.5-live-translate-preview",
        "target_language_code": "zh-Hant",
        "echo_target_language": True,
        "session_rotation_seconds": 480,
    },
    "caption": {"max_payload_length": 4096},
}

_METER = MeterReading(rms=0.1, peak=0.2, rms_dbfs=-20.0, peak_dbfs=-14.0, clipping=False)


class FakeSource:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0

    @property
    def active(self) -> bool:
        return self.started > self.stopped

    @property
    def latest_meter(self) -> MeterReading:
        return _METER

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


class FakeSession:
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


class FakeProvider:
    def __init__(self, events: list[TranslationEvent] | None = None) -> None:
        self.events = events or []
        self.connections = 0

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[FakeSession]:
        self.connections += 1
        session = FakeSession(self.events)
        try:
            yield session
        finally:
            await session.close()


def _runtime(
    *,
    sources: list[FakeSource] | None = None,
    provider: FakeProvider | None = None,
    settings: Mapping[str, Any] | None = None,
) -> tuple[PipelineRuntime, list[FakeSource], FakeProvider]:
    created: list[FakeSource] = sources if sources is not None else []
    used_provider = provider or FakeProvider()

    def source_factory(_settings: Mapping[str, Any]) -> FakeSource:
        source = FakeSource()
        created.append(source)
        return source

    def provider_factory(**kwargs: Any) -> FakeProvider:
        del kwargs
        return used_provider

    runtime = PipelineRuntime(
        settings or _SETTINGS,
        source_factory=source_factory,
        provider_factory=provider_factory,
    )
    return runtime, created, used_provider


async def _wait_until(predicate: Any, timeout: float = 1.0) -> None:
    async def poll() -> None:
        while not predicate():
            await asyncio.sleep(0.005)

    await asyncio.wait_for(poll(), timeout=timeout)


def test_start_without_api_key_fails_and_never_touches_audio() -> None:
    async def scenario() -> None:
        runtime, created, provider = _runtime()

        with pytest.raises(RuntimeCredentialError):
            await runtime.start()

        assert created == []
        assert provider.connections == 0
        assert runtime.running is False

    asyncio.run(scenario())


def test_start_then_stop_releases_the_audio_source() -> None:
    async def scenario() -> None:
        runtime, created, provider = _runtime()
        runtime.set_api_key("secret-api-key-value")

        await runtime.start()
        assert runtime.running is True
        await _wait_until(lambda: provider.connections == 1)

        await runtime.stop()
        assert runtime.running is False
        assert len(created) == 1
        assert created[0].started == 1
        assert created[0].stopped == 1

    asyncio.run(scenario())


def test_second_start_conflicts_without_disturbing_the_first() -> None:
    async def scenario() -> None:
        runtime, created, _provider = _runtime()
        runtime.set_api_key("secret-api-key-value")
        await runtime.start()

        with pytest.raises(RuntimeConflictError):
            await runtime.start()

        assert runtime.running is True
        assert len(created) == 1
        await runtime.stop()

    asyncio.run(scenario())


def test_stop_without_start_is_a_no_op() -> None:
    async def scenario() -> None:
        runtime, created, _provider = _runtime()
        await runtime.stop()
        assert runtime.running is False
        assert created == []

    asyncio.run(scenario())


def test_restart_builds_a_fresh_source() -> None:
    async def scenario() -> None:
        runtime, created, _provider = _runtime()
        runtime.set_api_key("secret-api-key-value")

        await runtime.start()
        await runtime.stop()
        await runtime.start()
        await runtime.stop()

        assert len(created) == 2
        assert [source.started for source in created] == [1, 1]
        assert [source.stopped for source in created] == [1, 1]

    asyncio.run(scenario())


def test_snapshot_exposes_status_caption_and_meter() -> None:
    async def scenario() -> None:
        events = [
            TranslationEvent(
                kind=TranslationEventKind.OUTPUT_TRANSCRIPTION,
                text="你好",
                language_code="zh-Hant",
                finished=False,
            )
        ]
        runtime, _created, _provider = _runtime(provider=FakeProvider(events))
        runtime.set_api_key("secret-api-key-value")

        await runtime.start()
        await _wait_until(lambda: runtime.snapshot().caption.text == "你好")

        snapshot = runtime.snapshot()
        assert snapshot.running is True
        assert snapshot.caption.status is CaptionStatus.PARTIAL
        assert snapshot.meter is not None and snapshot.meter.peak_dbfs == -14.0
        audio_status = snapshot.status.by_component(Component.AUDIO_SOURCE)
        assert audio_status is not None
        assert audio_status.state is ComponentState.RUNNING

        await runtime.stop()

    asyncio.run(scenario())


def test_snapshot_before_start_is_idle_without_meter() -> None:
    runtime, _created, _provider = _runtime()
    snapshot = runtime.snapshot()
    assert snapshot.running is False
    assert snapshot.meter is None
    assert snapshot.caption.status is CaptionStatus.IDLE
    audio_status = snapshot.status.by_component(Component.AUDIO_SOURCE)
    assert audio_status is not None and audio_status.state is ComponentState.IDLE


def test_api_key_never_reaches_an_output_surface() -> None:
    # The key has to live in memory somewhere, so introspection can always
    # find it. What must hold is that it never reaches a surface that gets
    # rendered, serialized or persisted.
    runtime, _created, _provider = _runtime()
    runtime.set_api_key("secret-api-key-value")

    assert runtime.has_api_key is True
    assert "secret-api-key-value" not in repr(runtime)
    assert "secret-api-key-value" not in str(runtime.settings)
    assert "secret-api-key-value" not in str(runtime.snapshot())

    runtime.clear_api_key()
    assert runtime.has_api_key is False


def test_blank_api_key_is_rejected_without_echoing_it() -> None:
    runtime, _created, _provider = _runtime()
    with pytest.raises(RuntimeCredentialError) as caught:
        runtime.set_api_key("   ")
    assert "   " not in str(caught.value).replace("Key", "")
    assert runtime.has_api_key is False


def test_audio_selection_update_enforces_source_exclusivity() -> None:
    runtime, _created, _provider = _runtime()

    runtime.update_audio_selection(
        source_kind="input_device", device_index=3, endpoint_index=None, channel=1
    )
    audio = runtime.settings["audio"]
    assert audio["source_kind"] == "input_device"
    assert audio["device_index"] == 3
    assert audio["loopback_endpoint_index"] is None

    runtime.update_audio_selection(
        source_kind="wasapi_loopback", device_index=None, endpoint_index=7, channel=None
    )
    audio = runtime.settings["audio"]
    assert audio["source_kind"] == "wasapi_loopback"
    assert audio["device_index"] is None
    assert audio["loopback_endpoint_index"] == 7


def test_audio_selection_cannot_change_while_running() -> None:
    async def scenario() -> None:
        runtime, _created, _provider = _runtime()
        runtime.set_api_key("secret-api-key-value")
        await runtime.start()

        with pytest.raises(RuntimeConflictError):
            runtime.update_audio_selection(
                source_kind="input_device",
                device_index=1,
                endpoint_index=None,
                channel=1,
            )

        await runtime.stop()

    asyncio.run(scenario())


def test_pipeline_failure_is_reported_as_a_safe_message() -> None:
    async def scenario() -> None:
        class ExplodingProvider:
            connections = 0

            @asynccontextmanager
            async def connect(self) -> AsyncIterator[object]:
                raise RuntimeError("raw SDK detail 0xdeadbeef")
                yield object()

        runtime, created, _provider = _runtime()
        runtime._provider_factory = lambda **_kwargs: ExplodingProvider()  # type: ignore[attr-defined]
        runtime.set_api_key("secret-api-key-value")

        await runtime.start()
        await _wait_until(lambda: runtime.running is False, timeout=2.0)

        error = runtime.last_error
        assert error is not None
        assert "0xdeadbeef" not in error
        assert created[0].stopped == 1

    asyncio.run(scenario())
