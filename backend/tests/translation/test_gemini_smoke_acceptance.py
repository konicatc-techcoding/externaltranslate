from __future__ import annotations

import asyncio
from typing import Any

import pytest

from backend.app.cli.gemini_smoke import GeminiSmokeError, run_translation_smoke
from backend.app.translation.models import TranslationEvent, TranslationEventKind


class FixedOutputPipeline:
    def __init__(self, text: str, language_code: str, finished: bool) -> None:
        self._event = TranslationEvent(
            kind=TranslationEventKind.OUTPUT_TRANSCRIPTION,
            text=text,
            language_code=language_code,
            finished=finished,
        )

    async def run(self, **kwargs: Any) -> None:
        await kwargs["event_sink"](self._event)


@pytest.mark.parametrize(
    ("text", "language_code", "finished"),
    [
        ("", "zh-Hant", True),
        ("hello", "en", True),
    ],
)
def test_smoke_rejects_empty_or_non_chinese_output(
    text: str, language_code: str, finished: bool
) -> None:
    async def scenario() -> None:
        with pytest.raises(GeminiSmokeError, match="繁體中文.*output transcription"):
            await run_translation_smoke(
                source=object(),
                provider=object(),
                duration_seconds=1.0,
                show_text=False,
                emit=lambda _payload: None,
                pipeline=FixedOutputPipeline(text, language_code, finished),
            )

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("text", "finished"),
    [
        ("你好", False),  # interim (unfinished) Chinese output proves translation
        ("你好", True),  # finished Chinese output
    ],
)
def test_smoke_accepts_non_empty_traditional_chinese_output(
    text: str, finished: bool
) -> None:
    async def scenario() -> None:
        report = await run_translation_smoke(
            source=object(),
            provider=object(),
            duration_seconds=1.0,
            show_text=False,
            emit=lambda _payload: None,
            pipeline=FixedOutputPipeline(text, "zh-Hant", finished),
        )
        assert report["output_transcription_events"] == 1
        assert report["finished_output_events"] == (1 if finished else 0)

    asyncio.run(scenario())
