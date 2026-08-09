from __future__ import annotations

from backend.app.captions.models import CaptionState


class CaptionStoreError(RuntimeError):
    """Raised when committing a caption state violates the store invariants."""


class CaptionStore:
    """Memory-only latest-caption store with monotonic revision/updated_at."""

    def __init__(self, initial: CaptionState | None = None) -> None:
        self._state = initial or CaptionState.initial()

    def snapshot(self) -> CaptionState:
        return self._state

    def commit(self, state: CaptionState) -> None:
        current = self._state
        if state.revision < current.revision:
            raise CaptionStoreError("字幕狀態 revision 不得倒退。")
        if state.updated_at < current.updated_at:
            raise CaptionStoreError("字幕狀態 updated_at 不得倒退。")
        self._state = state

    def reset(self) -> None:
        self._state = CaptionState.initial()