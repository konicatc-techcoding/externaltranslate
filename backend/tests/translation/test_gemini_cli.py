from __future__ import annotations

import asyncio
from typing import Any

import pytest

from backend.app.cli.gemini_smoke import (
    GeminiSmokeError,
    _parser,
    build_runtime_overrides,
    create_caption_observer,
    create_pipeline,
    create_runtime,
    main,
    render_event,
    resolve_api_key,
    run_translation_smoke,
)
from backend.app.status.models import Component, ComponentState
from backend.app.status.publisher import StatusPublisher
from backend.app.status.store import StatusStore
from backend.app.translation.models import TranslationEvent, TranslationEventKind

_SETTINGS: dict[str, Any] = {
    "gemini": {
        "model": "gemini-3.5-live-translate-preview",
        "target_language_code": "zh-Hant",
        "echo_target_language": True,
        "session_rotation_seconds": 480,
    },
    "caption": {"max_payload_length": 5},
}


def _output(text: str, *, finished: bool = False) -> TranslationEvent:
    return TranslationEvent(
        kind=TranslationEventKind.OUTPUT_TRANSCRIPTION,
        text=text,
        language_code="zh-Hant",
        finished=finished,
    )


def test_cli_has_no_api_key_argument_and_reads_key_from_environment() -> None:
    parser = _parser()
    args = parser.parse_args(["--source-kind", "wasapi_loopback"])

    assert not hasattr(args, "api_key")
    assert resolve_api_key(
        {"GEMINI_API_KEY": "secret-api-key-value"},
        prompt=lambda _message: pytest.fail("environment key should avoid prompt"),
    ) == "secret-api-key-value"


def test_cli_rejects_blank_api_key_without_leaking_it() -> None:
    with pytest.raises(GeminiSmokeError, match="API Key") as caught:
        resolve_api_key({}, prompt=lambda _message: "   ")

    assert "secret" not in str(caught.value).lower()


def test_cli_main_fails_safely_before_audio_when_key_is_missing() -> None:
    lines: list[str] = []

    exit_code = main(
        ["--source-kind", "wasapi_loopback", "--duration", "1"],
        environ={},
        prompt=lambda _message: "   ",
        emit=lines.append,
    )

    assert exit_code == 1
    assert len(lines) == 1
    assert '"status": "error"' in lines[0]
    assert "API Key" in lines[0]


def test_cli_builds_atomic_audio_source_overrides() -> None:
    assert build_runtime_overrides(
        source_kind="input_device",
        device_index=7,
        endpoint_index=None,
        channel=2,
    ) == {
        "audio": {
            "source_kind": "input_device",
            "device_index": 7,
            "loopback_endpoint_index": None,
            "channel": 2,
        }
    }
    assert build_runtime_overrides(
        source_kind="wasapi_loopback",
        device_index=None,
        endpoint_index=9,
        channel=None,
    ) == {
        "audio": {
            "source_kind": "wasapi_loopback",
            "device_index": None,
            "loopback_endpoint_index": 9,
        }
    }


def test_cli_creates_audio_source_and_provider_from_validated_settings() -> None:
    settings = {
        "audio": {"source_kind": "wasapi_loopback"},
        "gemini": {
            "model": "gemini-3.5-live-translate-preview",
            "target_language_code": "zh-Hant",
            "echo_target_language": True,
        },
    }
    source = object()
    provider = object()
    provider_kwargs: dict[str, object] = {}

    def source_factory(received: object) -> object:
        assert received is settings
        return source

    def provider_factory(**kwargs: object) -> object:
        provider_kwargs.update(kwargs)
        return provider

    created_source, created_provider = create_runtime(
        settings,
        api_key="secret-api-key-value",
        source_factory=source_factory,
        provider_factory=provider_factory,
    )

    assert created_source is source
    assert created_provider is provider
    assert provider_kwargs == {
        "api_key": "secret-api-key-value",
        "model": "gemini-3.5-live-translate-preview",
        "target_language_code": "zh-Hant",
        "echo_target_language": True,
    }


def test_cli_renders_transcript_metadata_and_requires_opt_in_for_text() -> None:
    event = TranslationEvent(
        kind=TranslationEventKind.OUTPUT_TRANSCRIPTION,
        text="敏感逐字稿",
        language_code="zh-Hant",
        finished=True,
    )

    metadata = render_event(event, show_text=False)
    visible = render_event(event, show_text=True)

    assert metadata == {
        "event": "output_transcription",
        "language_code": "zh-Hant",
        "finished": True,
        "text_length": 5,
    }
    assert "text" not in metadata
    assert visible["text"] == "敏感逐字稿"


def test_run_translation_smoke_emits_events_and_requires_output_transcription() -> None:
    class FakePipeline:
        async def run(self, **kwargs: Any) -> None:
            await kwargs["event_sink"](
                TranslationEvent(
                    kind=TranslationEventKind.INPUT_TRANSCRIPTION,
                    text="hello",
                    language_code="en",
                    finished=True,
                )
            )
            await kwargs["event_sink"](
                TranslationEvent(
                    kind=TranslationEventKind.OUTPUT_TRANSCRIPTION,
                    text="你好",
                    language_code="zh-Hant",
                    finished=True,
                )
            )

    async def scenario() -> None:
        emitted: list[dict[str, object]] = []
        report = await run_translation_smoke(
            source=object(),
            provider=object(),
            duration_seconds=1.0,
            show_text=False,
            emit=emitted.append,
            pipeline=FakePipeline(),
        )

        assert report == {
            "input_transcription_events": 1,
            "output_transcription_events": 1,
            "finished_output_events": 1,
        }
        assert [item["event"] for item in emitted] == [
            "input_transcription",
            "output_transcription",
        ]
        assert all("text" not in item for item in emitted)

    asyncio.run(scenario())


def test_cli_parser_defaults_status_and_caption_flags_to_off() -> None:
    args = _parser().parse_args(["--source-kind", "wasapi_loopback"])
    assert args.status_events is False
    assert args.caption_state is False


def test_caption_observer_applies_configured_payload_limit() -> None:
    async def scenario() -> None:
        emitted: list[dict[str, Any]] = []
        observer = create_caption_observer(
            _SETTINGS, emit=emitted.append, show_text=False
        )

        await observer(_output("一二三四五六七八", finished=True))

        assert len(emitted) == 1
        payload = emitted[0]
        assert payload["status"] == "caption"
        assert payload["text_length"] == 5
        assert payload["caption_status"] == "final"
        assert "text" not in payload

    asyncio.run(scenario())


def test_caption_observer_shows_text_only_on_opt_in() -> None:
    async def scenario() -> None:
        emitted: list[dict[str, Any]] = []
        observer = create_caption_observer(
            _SETTINGS, emit=emitted.append, show_text=True
        )

        await observer(_output("一二三", finished=False))

        assert emitted[0]["text"] == "一二三"

    asyncio.run(scenario())


def test_caption_observer_ignores_events_without_state_change() -> None:
    async def scenario() -> None:
        emitted: list[dict[str, Any]] = []
        observer = create_caption_observer(_SETTINGS, emit=emitted.append)

        await observer(_output("一二", finished=False))
        await observer(_output("", finished=False))
        await observer(
            TranslationEvent(
                kind=TranslationEventKind.INPUT_TRANSCRIPTION,
                text="hello",
                language_code="en",
            )
        )

        assert len(emitted) == 1

    asyncio.run(scenario())


def test_caption_observer_publishes_caption_sink_status() -> None:
    async def scenario() -> None:
        store = StatusStore()
        publisher = StatusPublisher(store, now=lambda: 1.0)
        observer = create_caption_observer(_SETTINGS, status_publisher=publisher)

        await observer(_output("一二", finished=False))
        partial = store.last(Component.CAPTION_SINK)
        assert partial.state is ComponentState.ACTIVE
        assert partial.detail is not None and "reason=partial" in partial.detail

        await observer(_output("一二三", finished=True))
        final = store.last(Component.CAPTION_SINK)
        assert final.detail is not None and "reason=final" in final.detail

        await observer(TranslationEvent(kind=TranslationEventKind.SESSION_STOPPED))
        assert store.last(Component.CAPTION_SINK).state is ComponentState.ACTIVE

        await observer(_output("四", finished=False))
        await observer(TranslationEvent(kind=TranslationEventKind.SESSION_STOPPED))
        assert store.last(Component.CAPTION_SINK).state is ComponentState.RESET

    asyncio.run(scenario())


def test_caption_status_never_carries_caption_text() -> None:
    async def scenario() -> None:
        store = StatusStore()
        publisher = StatusPublisher(store, now=lambda: 1.0)
        observer = create_caption_observer(_SETTINGS, status_publisher=publisher)

        await observer(_output("機密", finished=True))

        detail = store.last(Component.CAPTION_SINK).detail or ""
        assert "機密" not in detail
        assert "text_length=2" in detail

    asyncio.run(scenario())


def test_create_pipeline_forwards_status_publisher() -> None:
    captured: dict[str, Any] = {}

    def pipeline_factory(**kwargs: Any) -> object:
        captured.update(kwargs)
        return object()

    publisher = StatusPublisher(StatusStore())
    create_pipeline(
        _SETTINGS, pipeline_factory=pipeline_factory, status_publisher=publisher
    )

    assert captured["session_rotation_seconds"] == 480
    assert captured["status_publisher"] is publisher


def test_run_translation_smoke_feeds_the_caption_observer() -> None:
    class FakePipeline:
        async def run(self, **kwargs: Any) -> None:
            await kwargs["event_sink"](_output("你好", finished=True))

    async def scenario() -> None:
        seen: list[TranslationEvent] = []

        async def caption_observer(event: TranslationEvent) -> None:
            seen.append(event)

        await run_translation_smoke(
            source=object(),
            provider=object(),
            duration_seconds=1.0,
            show_text=False,
            emit=lambda _payload: None,
            pipeline=FakePipeline(),
            caption_observer=caption_observer,
        )

        assert [event.kind for event in seen] == [
            TranslationEventKind.OUTPUT_TRANSCRIPTION
        ]

    asyncio.run(scenario())


def test_run_translation_smoke_rejects_missing_output_transcription() -> None:
    class InputOnlyPipeline:
        async def run(self, **kwargs: Any) -> None:
            await kwargs["event_sink"](
                TranslationEvent(
                    kind=TranslationEventKind.INPUT_TRANSCRIPTION,
                    text="hello",
                    language_code="en",
                    finished=True,
                )
            )

    async def scenario() -> None:
        with pytest.raises(GeminiSmokeError, match="未收到.*output transcription"):
            await run_translation_smoke(
                source=object(),
                provider=object(),
                duration_seconds=1.0,
                show_text=False,
                emit=lambda _payload: None,
                pipeline=InputOnlyPipeline(),
            )

    asyncio.run(scenario())
