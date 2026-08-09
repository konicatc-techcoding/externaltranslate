from __future__ import annotations

import pytest

from backend.app.status.models import (
    Component,
    ComponentState,
    ComponentStatus,
)
from backend.app.status.store import StatusStore, StatusStoreError


def _status(
    component: Component,
    state: ComponentState,
    updated_at: float,
) -> ComponentStatus:
    return ComponentStatus(
        component=component,
        state=state,
        updated_at=updated_at,
    )


def test_store_starts_with_every_component_idle() -> None:
    store = StatusStore()
    snapshot = store.snapshot()
    assert snapshot.revision == 0
    for component in Component:
        status = snapshot.by_component(component)
        assert status is not None
        assert status.state is ComponentState.IDLE
        assert status.revision == 0


def test_update_stamps_monotonic_revision() -> None:
    store = StatusStore()
    first = store.update(
        _status(Component.AUDIO_SOURCE, ComponentState.STARTING, 1.0)
    )
    second = store.update(
        _status(Component.GEMINI_PROVIDER, ComponentState.CONNECTING, 2.0)
    )
    assert first.revision == 1
    assert second.revision == 2
    assert store.snapshot().revision == 2


def test_last_returns_latest_status_per_component() -> None:
    store = StatusStore()
    store.update(_status(Component.AUDIO_SOURCE, ComponentState.STARTING, 1.0))
    store.update(_status(Component.AUDIO_SOURCE, ComponentState.RUNNING, 2.0))
    assert store.last(Component.AUDIO_SOURCE).state is ComponentState.RUNNING
    assert store.last(Component.CAPTION_SINK).state is ComponentState.IDLE


def test_update_rejects_updated_at_regression() -> None:
    store = StatusStore()
    store.update(_status(Component.AUDIO_SOURCE, ComponentState.RUNNING, 5.0))
    with pytest.raises(StatusStoreError, match="倒退"):
        store.update(_status(Component.AUDIO_SOURCE, ComponentState.STOPPED, 4.0))


def test_updated_at_regression_is_per_component() -> None:
    store = StatusStore()
    store.update(_status(Component.AUDIO_SOURCE, ComponentState.RUNNING, 5.0))
    later = store.update(
        _status(Component.CAPTION_SINK, ComponentState.ACTIVE, 1.0)
    )
    assert later.state is ComponentState.ACTIVE


def test_snapshot_is_immutable_between_updates() -> None:
    store = StatusStore()
    before = store.snapshot()
    store.update(_status(Component.AUDIO_SOURCE, ComponentState.RUNNING, 1.0))
    after = store.snapshot()
    audio_before = before.by_component(Component.AUDIO_SOURCE)
    audio_after = after.by_component(Component.AUDIO_SOURCE)
    assert audio_before is not None and audio_after is not None
    assert audio_before.state is ComponentState.IDLE
    assert audio_after.state is ComponentState.RUNNING
    assert before.revision == 0


def test_snapshot_covers_every_component() -> None:
    store = StatusStore()
    store.update(_status(Component.GEMINI_SESSION, ComponentState.ACTIVE, 1.0))
    statuses = store.snapshot().statuses
    assert {status.component for status in statuses} == set(Component)
