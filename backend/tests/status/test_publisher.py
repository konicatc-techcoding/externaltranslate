from __future__ import annotations

import itertools

import pytest

from backend.app.status.models import (
    Component,
    ComponentState,
    ComponentStatus,
    StatusError,
    StatusReason,
)
from backend.app.status.publisher import StatusPublisher, status_payload
from backend.app.status.store import StatusStore


def _publisher(
    sink: list[ComponentStatus] | None = None,
) -> tuple[StatusPublisher, StatusStore]:
    store = StatusStore()
    clock = itertools.count(1.0, 1.0)
    publisher = StatusPublisher(
        store,
        now=lambda: next(clock),
        sink=sink.append if sink is not None else None,
    )
    return publisher, store


def test_publish_updates_store_and_returns_stamped_status() -> None:
    publisher, store = _publisher()
    status = publisher.publish(
        Component.GEMINI_SESSION, ComponentState.ACTIVE, generation=3
    )
    assert status.revision == 1
    assert status.session_generation == 3
    assert store.last(Component.GEMINI_SESSION).state is ComponentState.ACTIVE


def test_publish_composes_detail_from_whitelisted_fields() -> None:
    publisher, _store = _publisher()
    status = publisher.publish(
        Component.GEMINI_PROVIDER,
        ComponentState.BACKOFF,
        attempt=2,
        delay_seconds=1.0,
        reason=StatusReason.ERROR,
    )
    assert status.detail is not None
    assert "attempt=2" in status.detail
    assert "delay_seconds=1.0" in status.detail
    assert "reason=error" in status.detail


def test_publish_without_fields_has_no_detail() -> None:
    publisher, _store = _publisher()
    status = publisher.publish(Component.AUDIO_SOURCE, ComponentState.STARTING)
    assert status.detail is None


def test_publish_rejects_unknown_field() -> None:
    publisher, _store = _publisher()
    with pytest.raises(StatusError, match="不支援"):
        publisher.publish(
            Component.CAPTION_SINK,
            ComponentState.ACTIVE,
            text="機密逐字稿",  # type: ignore[arg-type]
        )


def test_publish_rejects_transcript_like_fields() -> None:
    publisher, _store = _publisher()
    for forbidden in ("caption", "transcript", "api_key", "message"):
        with pytest.raises(StatusError):
            publisher.publish(
                Component.CAPTION_SINK,
                ComponentState.ACTIVE,
                **{forbidden: "secret"},  # type: ignore[arg-type]
            )


def test_publish_rejects_wrong_field_types() -> None:
    publisher, _store = _publisher()
    with pytest.raises(StatusError):
        publisher.publish(
            Component.GEMINI_PROVIDER,
            ComponentState.BACKOFF,
            attempt="2",  # type: ignore[arg-type]
        )
    with pytest.raises(StatusError):
        publisher.publish(
            Component.GEMINI_SESSION,
            ComponentState.ROTATING,
            reason="任意文字",  # type: ignore[arg-type]
        )
    with pytest.raises(StatusError):
        publisher.publish(
            Component.GEMINI_PROVIDER,
            ComponentState.BACKOFF,
            delay_seconds=-1.0,
        )


def test_publish_rejects_state_not_allowed_for_component() -> None:
    publisher, _store = _publisher()
    with pytest.raises(StatusError):
        publisher.publish(Component.AUDIO_SOURCE, ComponentState.FAIL_CLOSED)


def test_publish_notifies_sink_with_stamped_status() -> None:
    seen: list[ComponentStatus] = []
    publisher, _store = _publisher(seen)
    publisher.publish(Component.AUDIO_SOURCE, ComponentState.RUNNING)
    publisher.publish(Component.AUDIO_SOURCE, ComponentState.STOPPED)
    assert [status.state for status in seen] == [
        ComponentState.RUNNING,
        ComponentState.STOPPED,
    ]
    assert [status.revision for status in seen] == [1, 2]


def test_status_payload_is_metadata_only() -> None:
    publisher, _store = _publisher()
    status = publisher.publish(
        Component.GEMINI_SESSION,
        ComponentState.ROTATING,
        reason=StatusReason.GOAWAY,
        generation=2,
    )
    payload = status_payload(status)
    assert payload == {
        "status": "component",
        "component": "gemini_session",
        "state": "rotating",
        "detail": "generation=2 reason=goaway",
        "revision": 1,
        "session_generation": 2,
        "updated_at": 1.0,
    }
