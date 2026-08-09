from __future__ import annotations

from backend.app.captions.assembler import CaptionAssembler
from backend.app.captions.models import CaptionStatus
from backend.app.translation.models import TranslationEvent, TranslationEventKind


def output(text: str, *, finished: bool, language_code: str = "zh-Hant") -> TranslationEvent:
    return TranslationEvent(
        kind=TranslationEventKind.OUTPUT_TRANSCRIPTION,
        text=text,
        language_code=language_code,
        finished=finished,
    )


def started() -> TranslationEvent:
    return TranslationEvent(kind=TranslationEventKind.SESSION_STARTED)


def stopped() -> TranslationEvent:
    return TranslationEvent(kind=TranslationEventKind.SESSION_STOPPED)


def test_partial_grows_cumulatively_and_bumps_revision() -> None:
    a = CaptionAssembler()
    first = a.accept(output("你", finished=False))
    second = a.accept(output("你好", finished=False))
    assert first is not None and first.status is CaptionStatus.PARTIAL
    assert first.text == "你"
    assert first.revision == 1
    assert second is not None and second.text == "你好"
    assert second.revision == 2


def test_repeated_partial_is_deduped_without_revision_bump() -> None:
    a = CaptionAssembler()
    a.accept(output("你好", finished=False))
    current = a.current()
    again = a.accept(output("你好", finished=False))
    assert again is None
    assert a.current() is current
    assert a.current().revision == current.revision


def test_final_promotes_to_final_and_replaceable_by_next_partial() -> None:
    a = CaptionAssembler()
    a.accept(output("你好", finished=False))
    final = a.accept(output("你好", finished=True))
    assert final is not None and final.status is CaptionStatus.FINAL
    partial = a.accept(output("再見", finished=False))
    assert partial is not None and partial.status is CaptionStatus.PARTIAL
    assert partial.text == "再見"


def test_final_with_same_text_is_visible_status_change() -> None:
    a = CaptionAssembler()
    a.accept(output("你好", finished=False))
    before = a.current().revision
    final = a.accept(output("你好", finished=True))
    assert final is not None
    assert final.revision == before + 1


def test_empty_output_text_is_ignored() -> None:
    a = CaptionAssembler()
    a.accept(output("你好", finished=False))
    current = a.current()
    empty = a.accept(output("", finished=False))
    assert empty is None
    assert a.current() is current


def test_none_text_is_ignored() -> None:
    a = CaptionAssembler()
    event = TranslationEvent(
        kind=TranslationEventKind.OUTPUT_TRANSCRIPTION,
        text=None,
        language_code="zh-Hant",
        finished=True,
    )
    assert a.accept(event) is None


def test_input_transcription_is_ignored() -> None:
    a = CaptionAssembler()
    ev = TranslationEvent(
        kind=TranslationEventKind.INPUT_TRANSCRIPTION,
        text="hello",
        language_code="en",
        finished=False,
    )
    assert a.accept(ev) is None
    assert a.current().status is CaptionStatus.IDLE


def test_session_start_clears_unconfirmed_partial() -> None:
    a = CaptionAssembler()
    a.accept(output("你好", finished=False))
    reset = a.accept(started())
    assert reset is not None
    assert reset.status is CaptionStatus.IDLE
    assert reset.text == ""
    assert reset.session_generation == 1


def test_session_start_retains_confirmed_final() -> None:
    a = CaptionAssembler()
    a.accept(output("你好", finished=True))
    reset = a.accept(started())
    assert reset is not None
    assert reset.status is CaptionStatus.FINAL
    assert reset.text == "你好"
    assert reset.session_generation == 1


def test_session_stop_clears_partial_but_keeps_final() -> None:
    a = CaptionAssembler()
    a.accept(output("你好", finished=False))
    a.accept(stopped())
    assert a.current().status is CaptionStatus.IDLE
    a.accept(output("固定", finished=True))
    a.accept(stopped())
    assert a.current().status is CaptionStatus.FINAL
    assert a.current().text == "固定"


def test_oversized_partial_is_truncated() -> None:
    a = CaptionAssembler(max_payload_length=5)
    state = a.accept(output("abcdefgh", finished=False))
    assert state is not None and state.text == "abcde"


def test_control_characters_are_sanitized() -> None:
    a = CaptionAssembler()
    state = a.accept(output("你\x00好\x1b", finished=False))
    assert state is not None
    assert state.text == "你好"