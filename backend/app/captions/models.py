from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CaptionStatus(StrEnum):
    """Finality of the current caption text."""

    IDLE = "idle"
    PARTIAL = "partial"
    FINAL = "final"


@dataclass(frozen=True)
class CaptionState:
    """An immutable snapshot of the canonical caption.

    Fields are deliberately UI/vMix-neutral so downstream consumers do not
    need to understand provider transcription events.
    """

    revision: int
    status: CaptionStatus
    text: str
    language_code: str
    updated_at: float
    session_generation: int
    #: Display window produced by the formatter. ``text`` stays the canonical
    #: accumulated caption; ``lines`` is what a viewer sees, and every
    #: consumer (web overlay, vMix GT title) renders the same lines so their
    #: wrapping cannot diverge.
    lines: tuple[str, ...] = ()

    @classmethod
    def initial(cls) -> CaptionState:
        return cls(
            revision=0,
            status=CaptionStatus.IDLE,
            text="",
            language_code="",
            updated_at=0.0,
            session_generation=0,
            lines=(),
        )