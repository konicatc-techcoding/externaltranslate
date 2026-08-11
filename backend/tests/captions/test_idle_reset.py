from __future__ import annotations

from backend.app.captions.assembler import CaptionAssembler
from backend.app.translation.models import TranslationEvent, TranslationEventKind


class Clock:
    """A hand-wound monotonic clock, so a pause takes no real time."""

    def __init__(self, start: float = 1000.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def output(text: str) -> TranslationEvent:
    return TranslationEvent(
        kind=TranslationEventKind.OUTPUT_TRANSCRIPTION,
        text=text,
        language_code="zh-Hant",
        finished=False,
    )


def build(clock: Clock, *, idle_reset_ms: int) -> CaptionAssembler:
    return CaptionAssembler(
        chars_per_line=6,
        max_lines=5,
        idle_reset_ms=idle_reset_ms,
        now=clock,
    )


def test_a_pause_starts_the_next_caption_at_the_top() -> None:
    # The whole point: after a gap the window fills from line one again
    # instead of sliding, which is where more than two lines earns its keep.
    clock = Clock()
    assembler = build(clock, idle_reset_ms=2500)
    assembler.accept(output("我們現在開始。第二句話。第三句話。"))

    clock.advance(3.0)
    state = assembler.accept(output("新的一段。"))

    assert state is not None
    assert state.text == "新的一段。"
    assert state.lines == ("新的一段。",)


def test_a_short_gap_keeps_appending() -> None:
    clock = Clock()
    assembler = build(clock, idle_reset_ms=2500)
    assembler.accept(output("前半句"))

    clock.advance(1.0)
    state = assembler.accept(output("後半句"))

    assert state is not None
    assert state.text == "前半句後半句"


def test_the_screen_does_not_change_during_the_pause() -> None:
    # Nothing is cleared on a timer. A blank vMix input during a Q&A gap
    # reads as the translation having died; the reset waits for something
    # new to put on screen.
    clock = Clock()
    assembler = build(clock, idle_reset_ms=2500)
    before = assembler.accept(output("還在畫面上"))
    assert before is not None

    clock.advance(60.0)

    assert assembler.current() == before


def test_zero_turns_the_reset_off() -> None:
    clock = Clock()
    assembler = build(clock, idle_reset_ms=0)
    assembler.accept(output("前半句"))

    clock.advance(3600.0)
    state = assembler.accept(output("後半句"))

    assert state is not None
    assert state.text == "前半句後半句"


def test_the_reset_keeps_the_revision_monotonic_and_the_generation_put() -> None:
    # The store outlives the run and rejects a revision that goes backwards;
    # and a pause is not a new session.
    clock = Clock()
    assembler = build(clock, idle_reset_ms=2500)
    first = assembler.accept(output("第一段。"))
    assert first is not None

    clock.advance(3.0)
    second = assembler.accept(output("第二段。"))

    assert second is not None
    assert second.revision == first.revision + 1
    assert second.session_generation == first.session_generation


def test_the_threshold_can_be_changed_while_running() -> None:
    clock = Clock()
    assembler = build(clock, idle_reset_ms=2500)
    assembler.accept(output("第一段。"))
    assembler.set_layout(
        chars_per_line=6, max_lines=5, sentence_breaks=True, idle_reset_ms=10_000
    )

    clock.advance(3.0)
    state = assembler.accept(output("第二段。"))

    assert state is not None
    assert state.text == "第一段。第二段。"
