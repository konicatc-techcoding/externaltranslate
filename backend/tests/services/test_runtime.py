from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from copy import deepcopy
from typing import Any

import pytest

from backend.app.audio.models import MeterReading
from backend.app.captions.models import CaptionStatus
from backend.app.services.runtime import (
    PipelineRuntime,
    RuntimeConflictError,
    RuntimeCredentialError,
    RuntimeSelectionError,
)
from backend.app.status.models import Component, ComponentState
from backend.app.translation.base import TranslationProviderError
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
    user_settings_path: Any = None,
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
        user_settings_path=user_settings_path,
        # Never touch real hardware from a unit test; the device identity
        # lookup would otherwise enumerate this machine's audio devices.
        device_lister=lambda: [],
        loopback_lister=lambda: [],
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


def test_restart_after_captions_still_works() -> None:
    # The first run leaves caption revisions behind; a second run must not
    # collide with them. Restarting without any caption traffic would not
    # exercise this at all.
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
        await _wait_until(lambda: runtime.snapshot().caption.text.endswith("你好"))
        await runtime.stop()

        await runtime.start()
        await _wait_until(lambda: runtime.snapshot().caption.text.endswith("你好"))

        assert runtime.last_error is None
        assert runtime.running is True
        await runtime.stop()

    asyncio.run(scenario())


def test_caption_sink_status_follows_caption_updates() -> None:
    # Without this the control page shows 字幕輸出 = idle while captions stream.
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
        await _wait_until(lambda: runtime.snapshot().caption.revision > 1)

        sink = runtime.snapshot().status.by_component(Component.CAPTION_SINK)
        assert sink is not None
        assert sink.state is ComponentState.ACTIVE
        assert sink.detail is not None
        assert "reason=partial" in sink.detail
        assert "text_length=2" in sink.detail
        # metadata only: the caption itself never reaches a status payload
        assert "你好" not in sink.detail

        await runtime.stop()

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


def test_elapsed_time_runs_freezes_and_restarts_from_zero() -> None:
    async def scenario() -> None:
        runtime, _created, _provider = _runtime()
        runtime.set_api_key("secret-api-key-value")

        assert runtime.snapshot().elapsed_seconds == 0.0

        await runtime.start()
        await asyncio.sleep(0.05)
        while_running = runtime.snapshot().elapsed_seconds
        assert while_running > 0

        await runtime.stop()
        frozen = runtime.snapshot().elapsed_seconds
        assert frozen >= while_running
        await asyncio.sleep(0.05)
        # a stopped run keeps its final duration on screen
        assert runtime.snapshot().elapsed_seconds == frozen

        await runtime.start()
        assert runtime.snapshot().elapsed_seconds < frozen
        await runtime.stop()

    asyncio.run(scenario())


def test_elapsed_time_freezes_when_a_run_fails_on_its_own() -> None:
    async def scenario() -> None:
        class RejectingProvider:
            @asynccontextmanager
            async def connect(self) -> AsyncIterator[object]:
                raise TranslationProviderError("API權限不足", retryable=False)
                yield object()

        runtime, _created, _provider = _runtime()
        runtime._provider_factory = lambda **_kwargs: RejectingProvider()  # type: ignore[attr-defined]
        runtime.set_api_key("secret-api-key-value")

        await runtime.start()
        await _wait_until(lambda: runtime.running is False, timeout=2.0)

        frozen = runtime.snapshot().elapsed_seconds
        await asyncio.sleep(0.05)
        assert runtime.snapshot().elapsed_seconds == frozen

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


def test_caption_settings_persist_for_the_next_start(tmp_path: Any) -> None:
    # Restarting must not lose a caption the operator spent a show tuning.
    user_settings = tmp_path / "user.yaml"
    runtime, _created, _provider = _runtime(user_settings_path=user_settings)

    runtime.update_caption_layout(chars_per_line=12, max_lines=4, sentence_breaks=True)
    runtime.update_caption_style(
        {
            "font": "kai",
            "size": 64,
            "scroll": False,
            "scroll_ms": 400,
            "color": "#FFCC00",
            "outline_width": 4,
            "align": "center",
        }
    )

    import yaml

    stored = yaml.safe_load(user_settings.read_text(encoding="utf-8"))
    assert stored["caption"]["chars_per_line"] == 12
    assert stored["caption"]["max_lines"] == 4
    assert stored["caption"]["font"] == "kai"
    assert stored["caption"]["size"] == 64
    assert stored["caption"]["color"] == "#FFCC00"
    assert stored["caption"]["scroll"] is False
    assert stored["caption"]["scroll_ms"] == 400
    assert stored["caption"]["outline_width"] == 4
    assert stored["caption"]["align"] == "center"


def test_persistence_never_writes_the_api_key(tmp_path: Any) -> None:
    user_settings = tmp_path / "user.yaml"
    runtime, _created, _provider = _runtime(user_settings_path=user_settings)
    runtime.set_api_key("AIzaSyFAKEKEY")

    runtime.update_caption_layout(chars_per_line=12, max_lines=4, sentence_breaks=True)

    assert "AIzaSyFAKEKEY" not in user_settings.read_text(encoding="utf-8")
    assert "api_key" not in user_settings.read_text(encoding="utf-8")


def test_the_audio_device_index_is_never_persisted(tmp_path: Any) -> None:
    # A device index means different hardware on another machine, and changes
    # on replug even here; carrying it over would capture the wrong source.
    # Only the device identity is saved — see test_runtime_audio_identity.py.
    user_settings = tmp_path / "user.yaml"
    runtime, _created, _provider = _runtime(user_settings_path=user_settings)

    runtime.update_audio_selection(
        source_kind="input_device", device_index=7, endpoint_index=None, channel=1
    )

    stored = user_settings.read_text(encoding="utf-8")
    assert "device_index" not in stored
    assert "7" not in stored


def test_a_failing_write_does_not_break_the_setting_change(tmp_path: Any) -> None:
    # Persistence is a convenience; a read-only disk must not stop the
    # operator from adjusting captions mid-show.
    unwritable = tmp_path / "missing-dir" / "user.yaml"
    runtime, _created, _provider = _runtime(user_settings_path=unwritable)
    runtime._persist = _raise_os_error  # type: ignore[assignment]

    runtime.update_caption_layout(chars_per_line=12, max_lines=4, sentence_breaks=True)

    assert runtime.settings["caption"]["chars_per_line"] == 12


def _raise_os_error(*_args: Any, **_kwargs: Any) -> None:
    raise OSError("disk is read-only")


def test_clear_captions_empties_the_display_while_running() -> None:
    # Stale captions left on screen after a silent stretch mislead viewers;
    # clearing must not require stopping translation.
    async def scenario() -> None:
        events = [
            TranslationEvent(
                kind=TranslationEventKind.OUTPUT_TRANSCRIPTION,
                text="舊的字幕",
                language_code="zh-Hant",
                finished=False,
            )
        ]
        runtime, _created, _provider = _runtime(provider=FakeProvider(events))
        runtime.set_api_key("secret-api-key-value")
        await runtime.start()
        await _wait_until(lambda: runtime.snapshot().caption.text == "舊的字幕")

        before = runtime.snapshot().caption
        runtime.clear_captions()
        after = runtime.snapshot().caption

        assert after.text == ""
        assert after.lines == ()
        # the store rejects a revision that goes backwards, and the socket
        # only pushes when it moves
        assert after.revision > before.revision
        assert runtime.running is True

        sink = runtime.snapshot().status.by_component(Component.CAPTION_SINK)
        assert sink is not None
        assert sink.state is ComponentState.RESET

        await runtime.stop()

    asyncio.run(scenario())


def test_clear_captions_before_any_caption_is_harmless() -> None:
    runtime, _created, _provider = _runtime()
    runtime.clear_captions()
    assert runtime.snapshot().caption.text == ""


def test_caption_layout_can_change_while_running() -> None:
    # Unlike the audio source, layout must be adjustable mid-broadcast:
    # forcing a stop to re-flow captions is not acceptable on air.
    async def scenario() -> None:
        events = [
            TranslationEvent(
                kind=TranslationEventKind.OUTPUT_TRANSCRIPTION,
                text="一二三四五六",
                language_code="zh-Hant",
                finished=False,
            )
        ]
        runtime, _created, _provider = _runtime(provider=FakeProvider(events))
        runtime.set_api_key("secret-api-key-value")
        await runtime.start()
        await _wait_until(lambda: runtime.snapshot().caption.text == "一二三四五六")

        before = runtime.snapshot().caption
        runtime.update_caption_layout(chars_per_line=4, max_lines=2, sentence_breaks=True)
        after = runtime.snapshot().caption

        assert after.lines == ("一二三四", "五六")
        assert after.text == before.text
        assert after.revision > before.revision
        assert runtime.running is True
        assert runtime.settings["caption"]["chars_per_line"] == 4

        await runtime.stop()

    asyncio.run(scenario())


def test_caption_layout_rejects_out_of_range_values() -> None:
    runtime, _created, _provider = _runtime()
    original = runtime.settings["caption"]["chars_per_line"]

    for chars, lines in ((0, 2), (999, 2), (20, 0), (20, 99)):
        with pytest.raises(RuntimeSelectionError):
            runtime.update_caption_layout(
                chars_per_line=chars, max_lines=lines, sentence_breaks=True
            )

    assert runtime.settings["caption"]["chars_per_line"] == original


def test_caption_layout_comes_from_settings_at_startup() -> None:
    async def scenario() -> None:
        settings = deepcopy(_SETTINGS)
        settings["caption"] = {
            "max_payload_length": 4096,
            "chars_per_line": 4,
            "max_lines": 3,
        }
        events = [
            TranslationEvent(
                kind=TranslationEventKind.OUTPUT_TRANSCRIPTION,
                text="一二三四五六七八",
                language_code="zh-Hant",
                finished=False,
            )
        ]
        runtime, _created, _provider = _runtime(
            provider=FakeProvider(events), settings=settings
        )
        runtime.set_api_key("secret-api-key-value")
        await runtime.start()
        await _wait_until(lambda: runtime.snapshot().caption.lines != ())

        assert runtime.snapshot().caption.lines == ("一二三四", "五六七八")
        await runtime.stop()

    asyncio.run(scenario())


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


def test_permanent_credential_failure_stays_visible_as_fail_closed() -> None:
    async def scenario() -> None:
        class RejectingProvider:
            @asynccontextmanager
            async def connect(self) -> AsyncIterator[object]:
                raise TranslationProviderError("API權限不足", retryable=False)
                yield object()

        runtime, _created, _provider = _runtime()
        runtime._provider_factory = lambda **_kwargs: RejectingProvider()  # type: ignore[attr-defined]
        runtime.set_api_key("secret-api-key-value")

        await runtime.start()
        await _wait_until(lambda: runtime.running is False, timeout=2.0)

        provider_status = runtime.snapshot().status.by_component(
            Component.GEMINI_PROVIDER
        )
        assert provider_status is not None
        # A generic error here would hide an unrecoverable credential problem.
        assert provider_status.state is ComponentState.FAIL_CLOSED

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
