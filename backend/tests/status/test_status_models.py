from __future__ import annotations

import dataclasses

import pytest

from backend.app.status.models import (
    Component,
    ComponentState,
    ComponentStatus,
    RuntimeStatusSnapshot,
    StatusError,
)


def _status(
    component: Component = Component.GEMINI_SESSION,
    state: ComponentState = ComponentState.ACTIVE,
    **kwargs: object,
) -> ComponentStatus:
    payload: dict[str, object] = {
        "component": component,
        "state": state,
        "detail": "generation=3",
        "updated_at": 1.0,
        "revision": 1,
        "session_generation": 3,
    }
    payload.update(kwargs)
    return ComponentStatus(**payload)  # type: ignore[arg-type]


def test_component_and_state_are_str_enums() -> None:
    assert Component.AUDIO_SOURCE == "audio_source"
    assert Component.GEMINI_PROVIDER == "gemini_provider"
    assert Component.GEMINI_SESSION == "gemini_session"
    assert Component.CAPTION_SINK == "caption_sink"
    assert ComponentState.CONNECTED == "connected"
    assert ComponentState.FAIL_CLOSED == "fail_closed"


def test_component_status_is_frozen_snapshot() -> None:
    status = _status()
    assert dataclasses.is_dataclass(status)
    with pytest.raises(dataclasses.FrozenInstanceError):
        status.detail = "x"  # type: ignore[misc]


def test_component_status_defaults_are_metadata_only() -> None:
    status = ComponentStatus(
        component=Component.AUDIO_SOURCE,
        state=ComponentState.IDLE,
        updated_at=0.0,
    )
    assert status.detail is None
    assert status.revision == 0
    assert status.session_generation is None


def test_component_status_rejects_state_not_allowed_for_component() -> None:
    with pytest.raises(StatusError, match="狀態"):
        _status(component=Component.AUDIO_SOURCE, state=ComponentState.FAIL_CLOSED)


def test_component_status_allows_shared_states() -> None:
    for component in Component:
        assert _status(component=component, state=ComponentState.IDLE, detail=None)
        assert _status(component=component, state=ComponentState.ERROR, detail=None)


def test_component_status_rejects_negative_revision() -> None:
    with pytest.raises(StatusError):
        _status(revision=-1)


def test_snapshot_query_by_component() -> None:
    audio = _status(component=Component.AUDIO_SOURCE, state=ComponentState.RUNNING)
    session = _status()
    snapshot = RuntimeStatusSnapshot(revision=7, statuses=(audio, session))
    assert snapshot.by_component(Component.AUDIO_SOURCE) is audio
    assert snapshot.by_component(Component.GEMINI_SESSION) is session
    assert snapshot.by_component(Component.CAPTION_SINK) is None


def test_snapshot_is_frozen_and_immutable_sequence() -> None:
    snapshot = RuntimeStatusSnapshot(revision=1, statuses=(_status(),))
    assert dataclasses.is_dataclass(snapshot)
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.revision = 2  # type: ignore[misc]
    assert isinstance(snapshot.statuses, tuple)
