from __future__ import annotations

import asyncio
from typing import Any

import pytest

from backend.app.cli.gemini_smoke import (
    GeminiSmokeError,
    _parser,
    build_runtime_overrides,
    create_runtime,
    main,
    render_event,
    resolve_api_key,
    run_translation_smoke,
)
from backend.app.translation.models import TranslationEvent, TranslationEventKind


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
