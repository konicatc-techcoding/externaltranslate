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


def test_output_fragments_are_appended_into_one_caption() -> None:
    # Confirmed against real Gemini Live output on 2026-08-09: each
    # output_transcription carries only the newly translated fragment.
    a = CaptionAssembler()
    first = a.accept(output("自然的、", finished=False))
    second = a.accept(output("真實的對話。", finished=False))
    assert first is not None and first.status is CaptionStatus.PARTIAL
    assert first.text == "自然的、"
    assert first.revision == 1
    assert second is not None and second.text == "自然的、真實的對話。"
    assert second.revision == 2


def test_repeated_fragment_is_appended_not_deduplicated() -> None:
    # With delta fragments an identical payload is new speech, not a repeat.
    a = CaptionAssembler()
    a.accept(output("好", finished=False))
    again = a.accept(output("好", finished=False))
    assert again is not None
    assert again.text == "好好"


def test_finished_fragment_promotes_to_final() -> None:
    a = CaptionAssembler()
    a.accept(output("你好", finished=False))
    final = a.accept(output("嗎？", finished=True))
    assert final is not None
    assert final.status is CaptionStatus.FINAL
    assert final.text == "你好嗎？"


def test_fragment_after_final_starts_a_new_caption() -> None:
    a = CaptionAssembler()
    a.accept(output("你好。", finished=True))
    partial = a.accept(output("再見", finished=False))
    assert partial is not None
    assert partial.status is CaptionStatus.PARTIAL
    assert partial.text == "再見"


def test_caption_keeps_the_most_recent_payload_window() -> None:
    # Trim from the front: an appended caption must never freeze once it
    # reaches the payload limit.
    a = CaptionAssembler(max_payload_length=5)
    a.accept(output("一二三", finished=False))
    state = a.accept(output("四五六", finished=False))
    assert state is not None
    assert state.text == "二三四五六"


def test_oversized_single_fragment_keeps_its_tail() -> None:
    a = CaptionAssembler(max_payload_length=5)
    state = a.accept(output("一二三四五六七八", finished=False))
    assert state is not None
    assert state.text == "四五六七八"


def test_empty_output_text_is_ignored() -> None:
    a = CaptionAssembler()
    a.accept(output("你好", finished=False))
    current = a.current()
    empty = a.accept(output("", finished=False))
    assert empty is None
    assert a.current() is current


def test_whitespace_only_fragment_does_not_start_a_caption() -> None:
    a = CaptionAssembler()
    assert a.accept(output("   ", finished=False)) is None
    assert a.current().status is CaptionStatus.IDLE


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


def test_fragment_after_session_reset_starts_a_new_caption() -> None:
    a = CaptionAssembler()
    a.accept(output("你好", finished=False))
    a.accept(started())
    state = a.accept(output("再見", finished=False))
    assert state is not None
    assert state.text == "再見"


def test_session_stop_clears_partial_but_keeps_final() -> None:
    a = CaptionAssembler()
    a.accept(output("你好", finished=False))
    a.accept(stopped())
    assert a.current().status is CaptionStatus.IDLE
    a.accept(output("固定", finished=True))
    a.accept(stopped())
    assert a.current().status is CaptionStatus.FINAL
    assert a.current().text == "固定"


def test_reset_clears_the_caption_but_keeps_revisions_monotonic() -> None:
    # A new run must not restart revisions: a CaptionStore that outlives the
    # run rejects a regression, which would break the second Start.
    a = CaptionAssembler()
    a.accept(output("你好", finished=True))
    before = a.current()

    cleared = a.reset()

    assert cleared.status is CaptionStatus.IDLE
    assert cleared.text == ""
    assert cleared.revision > before.revision
    assert a.current() is cleared


def test_fragments_after_reset_accumulate_from_empty() -> None:
    a = CaptionAssembler()
    a.accept(output("舊的", finished=True))
    a.reset()
    state = a.accept(output("新的", finished=False))

    assert state is not None
    assert state.text == "新的"


def test_state_carries_display_lines_alongside_canonical_text() -> None:
    a = CaptionAssembler(chars_per_line=3, max_lines=2)
    state = a.accept(output("一二三四五六七八", finished=False))

    assert state is not None
    # text stays the canonical accumulated tail; lines are the display window
    assert state.text == "一二三四五六七八"
    assert state.lines == ("四五六", "七八")


def test_display_window_keeps_only_the_most_recent_lines() -> None:
    a = CaptionAssembler(chars_per_line=2, max_lines=2)
    a.accept(output("一二三四", finished=False))
    state = a.accept(output("五六", finished=False))

    assert state is not None
    assert state.lines == ("三四", "五六")


def test_session_boundary_retains_lines_with_the_retained_final() -> None:
    # The final text survives rotation, so its lines must survive with it —
    # otherwise the caption text stays while the display goes blank.
    a = CaptionAssembler(chars_per_line=3, max_lines=2)
    a.accept(output("一二三四", finished=True))
    a.accept(stopped())

    # accept() may return None here (nothing observable changed); what matters
    # is that the retained final keeps both its text and its wrapped lines.
    retained = a.current()
    assert retained.text == "一二三四"
    assert retained.lines == ("一二三", "四")


def test_session_boundary_clearing_a_partial_also_clears_lines() -> None:
    a = CaptionAssembler(chars_per_line=3, max_lines=2)
    a.accept(output("一二三四", finished=False))
    cleared = a.accept(stopped())

    assert cleared is not None
    assert cleared.text == ""
    assert cleared.lines == ()


def test_reset_clears_lines() -> None:
    a = CaptionAssembler(chars_per_line=3, max_lines=2)
    a.accept(output("一二三", finished=True))
    assert a.reset().lines == ()


def test_layout_change_reflows_immediately_and_bumps_revision() -> None:
    a = CaptionAssembler(chars_per_line=6, max_lines=2)
    a.accept(output("一二三四五六七八九", finished=False))
    before = a.current()

    after = a.set_layout(chars_per_line=3, max_lines=2)

    assert after.text == before.text
    assert after.lines == ("四五六", "七八九")
    # without a new revision the socket would not push the reflow to the UI
    assert after.revision == before.revision + 1
    assert a.current() is after


def test_layout_change_on_an_empty_caption_is_safe() -> None:
    a = CaptionAssembler(chars_per_line=6, max_lines=2)
    state = a.set_layout(chars_per_line=4, max_lines=3)
    assert state.lines == ()
    assert state.text == ""


def test_control_characters_are_sanitized() -> None:
    a = CaptionAssembler()
    state = a.accept(output("你\x00好\x1b", finished=False))
    assert state is not None
    assert state.text == "你好"
