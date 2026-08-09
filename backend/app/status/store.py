from __future__ import annotations

import dataclasses

from backend.app.status.models import (
    Component,
    ComponentStatus,
    RuntimeStatusSnapshot,
)


class StatusStoreError(RuntimeError):
    """Raised when a status update violates the store invariants."""


class StatusStore:
    """Memory-only latest-status-per-component store.

    The store owns the monotonic revision counter so callers cannot stamp a
    stale revision; Stage 4 can use it to send only what a client has not
    seen yet. Nothing is persisted: statuses live for the process only.
    """

    def __init__(self) -> None:
        self._statuses: dict[Component, ComponentStatus] = {
            component: ComponentStatus.idle(component) for component in Component
        }
        self._revision = 0

    def update(self, status: ComponentStatus) -> ComponentStatus:
        current = self._statuses[status.component]
        if status.updated_at < current.updated_at:
            raise StatusStoreError(
                f"元件 {status.component.value} 的 status updated_at 不得倒退。"
            )
        self._revision += 1
        stamped = dataclasses.replace(status, revision=self._revision)
        self._statuses[status.component] = stamped
        return stamped

    def last(self, component: Component) -> ComponentStatus:
        return self._statuses[component]

    def snapshot(self) -> RuntimeStatusSnapshot:
        return RuntimeStatusSnapshot(
            revision=self._revision,
            statuses=tuple(self._statuses[component] for component in Component),
        )
