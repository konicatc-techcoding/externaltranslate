from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TranslationEventKind(StrEnum):
    SESSION_STARTED = "session_started"
    SESSION_EXPIRING = "session_expiring"
    INPUT_TRANSCRIPTION = "input_transcription"
    OUTPUT_TRANSCRIPTION = "output_transcription"
    SESSION_STOPPED = "session_stopped"


@dataclass(frozen=True)
class TranslationEvent:
    kind: TranslationEventKind
    text: str | None = None
    language_code: str | None = None
    finished: bool | None = None
