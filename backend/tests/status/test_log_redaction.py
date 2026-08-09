from __future__ import annotations

import json
import logging

import pytest

from backend.app.status.models import Component, ComponentState, StatusError, StatusReason
from backend.app.status.publisher import STATUS_LOGGER_NAME, StatusPublisher, status_payload
from backend.app.status.store import StatusStore

_SECRET = "AIzaSyFAKEKEYFAKEKEYFAKEKEY"
_TRANSCRIPT = "這是不該外洩的逐字稿內容"


def test_log_record_contains_component_and_state(
    caplog: pytest.LogCaptureFixture,
) -> None:
    publisher = StatusPublisher(StatusStore(), now=lambda: 1.0)
    with caplog.at_level(logging.INFO, logger=STATUS_LOGGER_NAME):
        publisher.publish(
            Component.GEMINI_SESSION, ComponentState.ACTIVE, generation=1
        )
    record = caplog.records[-1]
    assert record.name == STATUS_LOGGER_NAME
    assert "component=gemini_session" in record.getMessage()
    assert "state=active" in record.getMessage()


def test_transcript_and_credentials_cannot_reach_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    publisher = StatusPublisher(StatusStore(), now=lambda: 1.0)
    with caplog.at_level(logging.INFO, logger=STATUS_LOGGER_NAME):
        with pytest.raises(StatusError):
            publisher.publish(
                Component.CAPTION_SINK,
                ComponentState.ACTIVE,
                text=_TRANSCRIPT,  # type: ignore[arg-type]
            )
        with pytest.raises(StatusError):
            publisher.publish(
                Component.GEMINI_PROVIDER,
                ComponentState.FAIL_CLOSED,
                api_key=_SECRET,  # type: ignore[arg-type]
            )
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert _TRANSCRIPT not in rendered
    assert _SECRET not in rendered


def test_caption_status_log_never_includes_caption_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    publisher = StatusPublisher(StatusStore(), now=lambda: 1.0)
    with caplog.at_level(logging.INFO, logger=STATUS_LOGGER_NAME):
        status = publisher.publish(
            Component.CAPTION_SINK,
            ComponentState.ACTIVE,
            reason=StatusReason.FINAL,
            text_length=len(_TRANSCRIPT),
        )
    rendered = caplog.records[-1].getMessage()
    assert "text_length=12" in rendered
    assert _TRANSCRIPT not in rendered
    assert _TRANSCRIPT not in json.dumps(status_payload(status), ensure_ascii=False)
