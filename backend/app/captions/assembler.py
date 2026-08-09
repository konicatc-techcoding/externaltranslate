from __future__ import annotations

import time
from collections.abc import Callable

from backend.app.captions.models import CaptionState, CaptionStatus
from backend.app.captions.sanitizer import sanitize_caption
from backend.app.captions.store import CaptionStore
from backend.app.translation.models import TranslationEvent, TranslationEventKind

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

    Event semantics (confirmed during Stage 2 real smoke): output transcription
    ``text`` is a cumulative snapshot, ``finished`` marks finality. A new output
    event replaces the pending text; ``finished=True`` promotes to final. A
    session boundary clears unconfirmed partials but retains the confirmed final
    so the caption does not blank out during rotation.
    """

    def __init__(
        self,
        *,
        max_payload_length: int = 4096,
        now: _Now | None = None,
    ) -> None:
        self._max_payload_length = max_payload_length
        self._now = now or time.monotonic
        self._state = CaptionState.initial()

    def current(self) -> CaptionState:
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
        text = sanitize_caption(event.text, max_payload_length=self._max_payload_length)
        if not text:
            return None
        status = CaptionStatus.FINAL if event.finished is True else CaptionStatus.PARTIAL
        state = self._state
        if text == state.text and status is state.status:
            return None  # deduplicate repeated partial/final snapshots
        next_state = CaptionState(
            revision=state.revision + 1,
            status=status,
            text=text,
            language_code=event.language_code or state.language_code,
            updated_at=self._now(),
            session_generation=state.session_generation,
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