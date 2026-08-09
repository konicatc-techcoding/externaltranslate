from __future__ import annotations


class CaptionSanitizationError(ValueError):
    """Raised when caption payload is not a string or cannot be sanitized."""


def sanitize_caption(text: object, *, max_payload_length: int) -> str:
    """Return a text-node-safe string bounded to ``max_payload_length``.

    Removes non-printable control characters while keeping printable text,
    newlines, tabs and carriage returns. Rejects non-string input with a typed
    error so downstream never renders unexpected types.

    Oversized payloads keep their **tail**: captions accumulate over time, so
    the most recent speech is what a viewer needs to see.
    """
    if not isinstance(text, str):
        raise CaptionSanitizationError("字幕內容必須是字串。")
    cleaned = "".join(ch for ch in text if ch.isprintable() or ch in "\n\r\t")
    if len(cleaned) > max_payload_length:
        cleaned = cleaned[-max_payload_length:]
    return cleaned