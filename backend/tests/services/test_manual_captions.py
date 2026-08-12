from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
import yaml

from backend.app.services.runtime import PipelineRuntime, RuntimeSelectionError
from backend.tests.outputs.fake_vmix import FakeInput, FakeVmix

_TRANSLATION = FakeInput(
    guid="877bb3e7-58bd-46a1-85ce-0d673aec6bf5",
    number=1,
    name="翻譯字幕",
    text_fields=("Line1.Text", "Line2.Text"),
)
_MANUAL = FakeInput(
    guid="11111111-2222-3333-4444-555555555555",
    number=2,
    name="手動字幕",
    text_fields=("Manual1.Text", "Manual2.Text"),
)


def _settings(server: FakeVmix, **vmix: Any) -> dict[str, Any]:
    block: dict[str, Any] = {
        "host": "127.0.0.1",
        "port": server.port,
        "input_guid": _TRANSLATION.guid,
        "input_name": _TRANSLATION.name,
        "fields": ["Line1.Text", "Line2.Text"],
        "min_interval_ms": 50,
        "timeout_ms": 500,
        "manual_input_guid": _MANUAL.guid,
        "manual_input_name": _MANUAL.name,
        "manual_fields": ["Manual1.Text", "Manual2.Text"],
    }
    block.update(vmix)
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
        "caption": {"max_payload_length": 4096, "chars_per_line": 10, "max_lines": 2},
        "vmix": block,
        "features": {"vmix_output": True},
    }


def _runtime(settings: dict[str, Any], **kwargs: Any) -> PipelineRuntime:
    return PipelineRuntime(
        settings,
        source_factory=lambda _settings: pytest.fail("source must not be built"),
        provider_factory=lambda **_kw: pytest.fail("provider must not be built"),
        device_lister=lambda: [],
        loopback_lister=lambda: [],
        **kwargs,
    )


def test_manual_text_reaches_its_own_title() -> None:
    async def scenario() -> None:
        with FakeVmix([_TRANSLATION, _MANUAL]) as server:
            runtime = _runtime(_settings(server))

            lines = await runtime.send_manual_caption("請稍候")
            await runtime.close_manual_output()

            written = [(call.input, call.field, call.value) for call in server.calls]

        assert lines == ["請稍候"]
        assert written[0][0] == _MANUAL.guid
        assert written[0][1] == "Manual1.Text"
        assert written[0][2] == "請稍候"
        # The unused field is blanked, or the previous message's second line
        # stays underneath the new one.
        assert written[1][2] == ""

    asyncio.run(scenario())


def test_it_works_while_the_translation_is_not_running() -> None:
    # The whole point of a manual caption: someone may be operating it on a
    # machine that never starts a translation at all.
    async def scenario() -> None:
        with FakeVmix([_TRANSLATION, _MANUAL]) as server:
            runtime = _runtime(_settings(server))
            assert runtime.running is False

            await runtime.send_manual_caption("節目稍後開始")
            await runtime.close_manual_output()

            assert any(call.value == "節目稍後開始" for call in server.calls)

    asyncio.run(scenario())


def test_sending_again_replaces_what_is_on_air() -> None:
    async def scenario() -> None:
        with FakeVmix([_TRANSLATION, _MANUAL]) as server:
            runtime = _runtime(_settings(server))

            await runtime.send_manual_caption("第一則")
            await runtime.send_manual_caption("第二則")
            await runtime.close_manual_output()

            values = [call.value for call in server.calls if call.value]

        assert values[-1] == "第二則"

    asyncio.run(scenario())


def test_the_translation_title_is_never_touched() -> None:
    async def scenario() -> None:
        with FakeVmix([_TRANSLATION, _MANUAL]) as server:
            runtime = _runtime(_settings(server))

            await runtime.send_manual_caption("請稍候")
            await runtime.clear_manual_caption()
            await runtime.close_manual_output()

            targets = {call.input for call in server.calls}

        assert targets == {_MANUAL.guid}

    asyncio.run(scenario())


def test_long_text_keeps_the_beginning_and_says_it_did_not_fit() -> None:
    # A typed message is fixed text. Dropping the front of it — which is what
    # the translation window does — would hide the part that matters.
    async def scenario() -> None:
        with FakeVmix([_TRANSLATION, _MANUAL]) as server:
            # Stated rather than inherited: the width this wraps at is the
            # manual title's own, so the test says which one it means.
            runtime = _runtime(_settings(server, manual_chars_per_line=10))

            lines = await runtime.send_manual_caption("一二三四五六七八九十" * 4)
            await runtime.close_manual_output()

        assert len(lines) == 2
        assert lines[0].startswith("一二三")
        assert runtime.manual_overflowed is True

    asyncio.run(scenario())


def test_without_a_chosen_manual_title_it_refuses() -> None:
    async def scenario() -> None:
        with FakeVmix([_TRANSLATION, _MANUAL]) as server:
            runtime = _runtime(
                _settings(server, manual_input_guid=None, manual_input_name=None)
            )

            with pytest.raises(RuntimeSelectionError):
                await runtime.send_manual_caption("請稍候")

    asyncio.run(scenario())


def test_the_saved_boxes_survive_a_restart(tmp_path: Path) -> None:
    user_settings = tmp_path / "user.yaml"
    with FakeVmix([_TRANSLATION, _MANUAL]) as server:
        runtime = _runtime(_settings(server), user_settings_path=user_settings)

        runtime.update_vmix_settings(
            {"manual_slots": ["請稍候", "節目稍後開始", "", "", ""]}
        )

    stored = yaml.safe_load(user_settings.read_text(encoding="utf-8"))
    assert stored["vmix"]["manual_slots"][1] == "節目稍後開始"


def test_the_manual_title_may_not_be_the_translation_title() -> None:
    with FakeVmix([_TRANSLATION, _MANUAL]) as server:
        runtime = _runtime(_settings(server))

        with pytest.raises(RuntimeSelectionError):
            runtime.update_vmix_settings({"manual_input_guid": _TRANSLATION.guid})


def test_the_manual_line_width_is_its_own() -> None:
    # Changing how the translation wraps must not silently rewrap a prepared
    # message: they are different titles with different boxes.
    async def scenario() -> None:
        with FakeVmix([_TRANSLATION, _MANUAL]) as server:
            settings = _settings(server, manual_chars_per_line=4)
            runtime = _runtime(settings)

            lines = await runtime.send_manual_caption("一二三四五六七八")
            await runtime.close_manual_output()

        # Four full-width characters per line, not the translation's ten.
        assert lines == ["一二三四", "五六七八"]

    asyncio.run(scenario())


def test_the_translation_width_no_longer_moves_it() -> None:
    async def scenario() -> None:
        with FakeVmix([_TRANSLATION, _MANUAL]) as server:
            runtime = _runtime(_settings(server, manual_chars_per_line=4))
            runtime.update_caption_layout(
                chars_per_line=40, max_lines=2, sentence_breaks=True
            )

            lines = await runtime.send_manual_caption("一二三四五六七八")
            await runtime.close_manual_output()

        assert lines == ["一二三四", "五六七八"]

    asyncio.run(scenario())
