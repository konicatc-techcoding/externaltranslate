from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
import yaml

from backend.app.audio.models import MeterReading
from backend.app.services.runtime import PipelineRuntime, RuntimeSelectionError
from backend.app.status.models import Component, ComponentState
from backend.app.translation.models import TranslationEvent, TranslationEventKind
from backend.tests.outputs.fake_vmix import FakeInput, FakeVmix

_TITLE = FakeInput(
    guid="877bb3e7-58bd-46a1-85ce-0d673aec6bf5",
    number=1,
    name="字幕標題",
    text_fields=("Line1.Text", "Line2.Text"),
)

_METER = MeterReading(rms=0.1, peak=0.2, rms_dbfs=-20.0, peak_dbfs=-14.0, clipping=False)


class FakeSource:
    started = 0
    stopped = 0

    @property
    def active(self) -> bool:
        return True

    @property
    def latest_meter(self) -> MeterReading:
        return _METER

    def start(self) -> None:
        return

    def stop(self) -> None:
        return

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
    def __init__(self, events: list[TranslationEvent]) -> None:
        self.events = events

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[FakeSession]:
        session = FakeSession(self.events)
        try:
            yield session
        finally:
            await session.close()


def _caption(text: str) -> TranslationEvent:
    return TranslationEvent(
        kind=TranslationEventKind.OUTPUT_TRANSCRIPTION,
        text=text,
        language_code="zh-Hant",
        finished=False,
    )


def _settings(server: FakeVmix | None, *, enabled: bool, guid: str) -> dict[str, Any]:
    return {
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
        "caption": {"max_payload_length": 4096, "chars_per_line": 20, "max_lines": 2},
        "vmix": {
            "host": "127.0.0.1",
            "port": server.port if server is not None else 1,
            "input_guid": guid,
            "input_name": "字幕標題",
            "fields": ["Line1.Text", "Line2.Text"],
            "min_interval_ms": 50,
            "timeout_ms": 500,
        },
        "features": {"vmix_output": enabled},
    }


def _runtime(
    settings: Mapping[str, Any], *, user_settings_path: Path | None = None
) -> PipelineRuntime:
    return PipelineRuntime(
        settings,
        source_factory=lambda _settings: FakeSource(),
        provider_factory=lambda **_kwargs: FakeProvider([_caption("你好嗎")]),
        user_settings_path=user_settings_path,
        device_lister=lambda: [],
        loopback_lister=lambda: [],
    )


async def _until(predicate: Any, timeout: float = 3.0) -> None:
    async def poll() -> None:
        while not predicate():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(poll(), timeout=timeout)


def test_caption_lines_reach_the_title_fields() -> None:
    async def scenario() -> None:
        with FakeVmix([_TITLE]) as server:
            runtime = _runtime(_settings(server, enabled=True, guid=_TITLE.guid))
            runtime.set_api_key("secret-api-key-value")

            await runtime.start()
            await _until(lambda: len(server.calls) >= 2)
            await runtime.stop()

            written = [call.value for call in server.calls]

        assert "你好嗎" in written

    asyncio.run(scenario())


def test_stopping_blanks_the_title() -> None:
    # The most visible failure of a caption integration: the last sentence
    # left frozen on air after translation stopped.
    async def scenario() -> None:
        with FakeVmix([_TITLE]) as server:
            runtime = _runtime(_settings(server, enabled=True, guid=_TITLE.guid))
            runtime.set_api_key("secret-api-key-value")

            await runtime.start()
            await _until(lambda: any(call.value == "你好嗎" for call in server.calls))
            await runtime.stop()

            tail = [call.value for call in server.calls[-2:]]

        assert tail == ["", ""]

    asyncio.run(scenario())


def test_clearing_captions_also_blanks_the_title() -> None:
    async def scenario() -> None:
        with FakeVmix([_TITLE]) as server:
            runtime = _runtime(_settings(server, enabled=True, guid=_TITLE.guid))
            runtime.set_api_key("secret-api-key-value")
            await runtime.start()
            await _until(lambda: any(call.value == "你好嗎" for call in server.calls))

            await runtime.clear_captions()
            cleared = [call.value for call in server.calls[-2:]]
            await runtime.stop()

        assert cleared == ["", ""]

    asyncio.run(scenario())


def test_a_dead_vmix_does_not_disturb_translation() -> None:
    # The whole point of the isolation: the web overlay is the primary output.
    async def scenario() -> None:
        with FakeVmix([_TITLE]) as server:
            settings = _settings(server, enabled=True, guid=_TITLE.guid)
        # server is closed: nothing is listening on that port any more
        runtime = _runtime(settings)
        runtime.set_api_key("secret-api-key-value")

        await runtime.start()
        await _until(lambda: runtime.snapshot().caption.text == "你好嗎")

        assert runtime.running is True
        assert runtime.last_error is None
        assert runtime.vmix_notice is not None  # said out loud, not swallowed
        await runtime.stop()

    asyncio.run(scenario())


def test_vmix_failing_mid_run_keeps_captions_flowing() -> None:
    async def scenario() -> None:
        with FakeVmix([_TITLE]) as server:
            runtime = _runtime(_settings(server, enabled=True, guid=_TITLE.guid))
            runtime.set_api_key("secret-api-key-value")
            await runtime.start()
            await _until(lambda: len(server.calls) >= 1)

            server.set_mode("server_error")
            await asyncio.sleep(0.2)

            assert runtime.running is True
            assert runtime.snapshot().caption.text == "你好嗎"
            await runtime.stop()

    asyncio.run(scenario())


def test_a_missing_input_disables_output_and_explains() -> None:
    async def scenario() -> None:
        with FakeVmix([_TITLE]) as server:
            runtime = _runtime(
                _settings(server, enabled=True, guid="00000000-0000-0000-0000-0000")
            )
            runtime.set_api_key("secret-api-key-value")

            await runtime.start()
            await _until(lambda: runtime.snapshot().caption.text == "你好嗎")
            notice = runtime.vmix_notice
            await runtime.stop()

        assert notice is not None
        assert "input" in notice

    asyncio.run(scenario())


def test_enabled_without_an_input_says_so() -> None:
    async def scenario() -> None:
        with FakeVmix([_TITLE]) as server:
            settings = _settings(server, enabled=True, guid=_TITLE.guid)
            settings["vmix"]["input_guid"] = None
            runtime = _runtime(settings)
            runtime.set_api_key("secret-api-key-value")

            await runtime.start()
            await _until(lambda: runtime.snapshot().caption.text == "你好嗎")
            notice = runtime.vmix_notice
            await runtime.stop()

        assert notice is not None

    asyncio.run(scenario())


def test_disabled_output_touches_nothing() -> None:
    async def scenario() -> None:
        with FakeVmix([_TITLE]) as server:
            runtime = _runtime(_settings(server, enabled=False, guid=_TITLE.guid))
            runtime.set_api_key("secret-api-key-value")

            await runtime.start()
            await _until(lambda: runtime.snapshot().caption.text == "你好嗎")
            await runtime.stop()

            calls = list(server.calls)

        assert calls == []

    asyncio.run(scenario())


def test_the_status_component_follows_the_output() -> None:
    async def scenario() -> None:
        with FakeVmix([_TITLE]) as server:
            runtime = _runtime(_settings(server, enabled=True, guid=_TITLE.guid))
            runtime.set_api_key("secret-api-key-value")
            await runtime.start()
            await _until(
                lambda: (
                    (item := runtime.snapshot().status.by_component(
                        Component.VMIX_OUTPUT
                    ))
                    is not None
                    and item.state is ComponentState.ACTIVE
                )
            )
            await runtime.stop()

        status = runtime.snapshot().status.by_component(Component.VMIX_OUTPUT)
        assert status is not None
        assert status.state is ComponentState.STOPPED

    asyncio.run(scenario())


def test_the_status_detail_never_carries_caption_text() -> None:
    async def scenario() -> None:
        with FakeVmix([_TITLE]) as server:
            runtime = _runtime(_settings(server, enabled=True, guid=_TITLE.guid))
            runtime.set_api_key("secret-api-key-value")
            await runtime.start()
            await _until(lambda: len(server.calls) >= 2)
            await runtime.stop()

        for status in runtime.snapshot().status.statuses:
            assert "你好嗎" not in str(status.detail)

    asyncio.run(scenario())


def test_vmix_settings_are_persisted(tmp_path: Path) -> None:
    user_settings = tmp_path / "user.yaml"
    with FakeVmix([_TITLE]) as server:
        runtime = _runtime(
            _settings(server, enabled=False, guid=_TITLE.guid),
            user_settings_path=user_settings,
        )
        runtime.update_vmix_settings({"fields": ["A.Text", "B.Text", "C.Text"]})
        runtime.set_vmix_enabled(True)

    stored = yaml.safe_load(user_settings.read_text(encoding="utf-8"))
    assert stored["vmix"]["fields"] == ["A.Text", "B.Text", "C.Text"]
    assert stored["features"]["vmix_output"] is True


def test_invalid_vmix_settings_are_refused(tmp_path: Path) -> None:
    with FakeVmix([_TITLE]) as server:
        runtime = _runtime(_settings(server, enabled=False, guid=_TITLE.guid))
        original = dict(runtime.settings["vmix"])

        with pytest.raises(RuntimeSelectionError):
            runtime.update_vmix_settings({"host": "http://example.com/api"})
        with pytest.raises(RuntimeSelectionError):
            runtime.update_vmix_settings({"fields": []})
        with pytest.raises(RuntimeSelectionError):
            runtime.update_vmix_settings({"nonsense": 1})

        assert dict(runtime.settings["vmix"]) == original
