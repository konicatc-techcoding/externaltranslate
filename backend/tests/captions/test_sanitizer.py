from __future__ import annotations

import pytest

from backend.app.captions.sanitizer import CaptionSanitizationError, sanitize_caption


def test_sanitize_keeps_normal_text() -> None:
    assert sanitize_caption("你好 world", max_payload_length=100) == "你好 world"


def test_sanitize_rejects_non_string() -> None:
    with pytest.raises(CaptionSanitizationError):
        sanitize_caption(None, max_payload_length=100)  # type: ignore[arg-type]
    with pytest.raises(CaptionSanitizationError):
        sanitize_caption(123, max_payload_length=100)  # type: ignore[arg-type]


def test_sanitize_removes_control_characters() -> None:
    cleaned = sanitize_caption("a\x00b\x1bESC", max_payload_length=100)
    assert cleaned == "abESC"


def test_sanitize_preserves_newline_tab_cr() -> None:
    cleaned = sanitize_caption("第一行\n第二行\t結尾\r!",
                               max_payload_length=100)
    assert cleaned == "第一行\n第二行\t結尾\r!"


def test_sanitize_truncates_to_max_payload_length() -> None:
    cleaned = sanitize_caption("abcdefghij", max_payload_length=5)
    assert cleaned == "abcde"


def test_sanitize_keeps_chinese_emoji() -> None:
    cleaned = sanitize_caption("中文🙂", max_payload_length=100)
    assert cleaned == "中文🙂"