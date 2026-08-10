from __future__ import annotations

import time
from collections.abc import Callable

from backend.app.captions.formatter import wrap_caption
from backend.app.captions.models import CaptionState, CaptionStatus
from backend.app.captions.sanitizer import sanitize_caption
from backend.app.captions.store import CaptionStore
from backend.app.translation.models import TranslationEvent, TranslationEventKind

DEFAULT_CHARS_PER_LINE = 20
DEFAULT_MAX_LINES = 2
DEFAULT_SENTENCE_BREAKS = True

_Now = Callable[[], float]

_SESSION_CLEAR = frozenset(
    {
        TranslationEventKind.SESSION_STARTED,
        TranslationEventKind.SESSION_EXPIRING,
        TranslationEventKind.SESSION_STOPPED,
    }
)


class CaptionAssembler:
    """Turn provider-neutral translation events into canonical CaptionState.

    Event semantics (confirmed against real Gemini Live output on 2026-08-09):
    each output transcription carries only the **newly translated fragment**,
    not a cumulative snapshot, so fragments are appended. ``finished=True``
    promotes the accumulated text to final and the next fragment starts a new
    caption. A session boundary clears unconfirmed partials but retains the
    confirmed final so the caption does not blank out during rotation.

    The accumulated text is trimmed from the front to ``max_payload_length``:
    continuous speech would otherwise grow without bound, and truncating the
    tail would freeze the caption at the limit.

    Every state also carries ``lines``: the accumulated text wrapped to
    ``chars_per_line`` full-width characters and windowed to the most recent
    ``max_lines``. Wrapping lives here rather than in each consumer so the web
    overlay and the vMix GT title cannot disagree about where a line breaks.
    """

    def __init__(
        self,
        *,
        max_payload_length: int = 4096,
        chars_per_line: int = DEFAULT_CHARS_PER_LINE,
        max_lines: int = DEFAULT_MAX_LINES,
        sentence_breaks: bool = DEFAULT_SENTENCE_BREAKS,
        now: _Now | None = None,
    ) -> None:
        self._max_payload_length = max_payload_length
        self._chars_per_line = chars_per_line
        self._max_lines = max_lines
        self._sentence_breaks = sentence_breaks
        self._now = now or time.monotonic
        self._state = CaptionState.initial()

    def current(self) -> CaptionState:
        return self._state

    def _wrap(self, text: str) -> tuple[str, ...]:
        return wrap_caption(
            text,
            chars_per_line=self._chars_per_line,
            max_lines=self._max_lines,
            sentence_breaks=self._sentence_breaks,
        )

    def set_layout(
        self,
        *,
        chars_per_line: int,
        max_lines: int,
        sentence_breaks: bool = DEFAULT_SENTENCE_BREAKS,
    ) -> CaptionState:
        """Re-flow the current caption for a new layout, without interrupting.

        The revision advances so downstream sockets push the new wrapping;
        an unchanged revision would leave the UI showing the old lines.
        """
        if chars_per_line < 1 or max_lines < 1:
            raise ValueError("chars_per_line 與 max_lines 必須大於 0。")
        self._chars_per_line = chars_per_line
        self._max_lines = max_lines
        self._sentence_breaks = sentence_breaks
        state = self._state
        self._state = CaptionState(
            revision=state.revision + 1,
            status=state.status,
            text=state.text,
            language_code=state.language_code,
            updated_at=self._now(),
            session_generation=state.session_generation,
            lines=self._wrap(state.text),
        )
        return self._state

    def reset(self) -> CaptionState:
        """Clear the caption for a new run, keeping the revision monotonic.

        A `CaptionStore` may outlive the run and rejects a revision that goes
        backwards, so a new run continues the counter instead of restarting it.
        """
        state = self._state
        self._state = CaptionState(
            revision=state.revision + 1,
            status=CaptionStatus.IDLE,
            text="",
            language_code=state.language_code,
            updated_at=self._now(),
            session_generation=state.session_generation,
            lines=(),
        )
        return self._state

    def accept(self, event: TranslationEvent) -> CaptionState | None:
        if event.kind is TranslationEventKind.OUTPUT_TRANSCRIPTION:
            return self._accept_output(event)
        if event.kind is TranslationEventKind.INPUT_TRANSCRIPTION:
            return None  # not used for the localized caption
        if event.kind in _SESSION_CLEAR:
            is_start = event.kind is TranslationEventKind.SESSION_STARTED
            return self._clear_unconfirmed(increment_generation=is_start)
        return None

    def _accept_output(self, event: TranslationEvent) -> CaptionState | None:
        if event.text is None:
            return None
        fragment = sanitize_caption(
            event.text, max_payload_length=self._max_payload_length
        )
        if not fragment:
            return None
        state = self._state
        # A confirmed final closes its caption, so the next fragment opens a
        # new one instead of extending finished text.
        pending = "" if state.status is not CaptionStatus.PARTIAL else state.text
        if not pending and not fragment.strip():
            return None  # never open a caption with whitespace alone
        text = (pending + fragment)[-self._max_payload_length :]
        status = CaptionStatus.FINAL if event.finished is True else CaptionStatus.PARTIAL
        next_state = CaptionState(
            revision=state.revision + 1,
            status=status,
            text=text,
            language_code=event.language_code or state.language_code,
            updated_at=self._now(),
            session_generation=state.session_generation,
            lines=self._wrap(text),
        )
        self._state = next_state
        return next_state

    def _clear_unconfirmed(self, *, increment_generation: bool) -> CaptionState | None:
        state = self._state
        generation = (
            state.session_generation + 1
            if increment_generation
            else state.session_generation
        )
        if state.status is CaptionStatus.FINAL:
            # retain the confirmed final so the caption does not blank during
            # rotation; only bump generation if a new session started.
            next_state = CaptionState(
                revision=state.revision + 1
                if generation != state.session_generation
                else state.revision,
                status=CaptionStatus.FINAL,
                text=state.text,
                language_code=state.language_code,
                updated_at=self._now(),
                session_generation=generation,
                lines=state.lines,
            )
        else:
            next_state = CaptionState(
                revision=state.revision + 1
                if state.revision > 0 or state.status is not CaptionStatus.IDLE
                else state.revision,
                status=CaptionStatus.IDLE,
                text="",
                language_code=state.language_code,
                updated_at=self._now(),
                session_generation=generation,
            )
        if next_state == state:
            return None
        self._state = next_state
        return next_state


class CaptionEventSink:
    """Adapter that feeds TranslationEvents into an assembler and commits the
    resulting CaptionState to a store. Usable directly as a
    ``TranslationEventSink`` passed to the pipeline.
    """

    def __init__(self, assembler: CaptionAssembler, store: CaptionStore) -> None:
        self._assembler = assembler
        self._store = store

    async def __call__(self, event: TranslationEvent) -> None:
        state = self._assembler.accept(event)
        if state is not None:
            self._store.commit(state)