from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from backend.app.translation.models import TranslationEvent, TranslationEventKind


def test_transcription_event_preserves_provider_neutral_metadata() -> None:
    event = TranslationEvent(
        kind=TranslationEventKind.OUTPUT_TRANSCRIPTION,
        text="測試字幕",
        language_code="zh-Hant",
        finished=False,
    )

    assert event.kind is TranslationEventKind.OUTPUT_TRANSCRIPTION
    assert event.text == "測試字幕"
    assert event.language_code == "zh-Hant"
    assert event.finished is False
    assert not hasattr(event, "audio")
    assert not hasattr(event, "raw_response")

    with pytest.raises(FrozenInstanceError):
        event.text = "不可修改"  # type: ignore[misc]
