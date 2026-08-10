from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class StatusError(ValueError):
    """Raised when a runtime status value violates the status contract."""


class StatusReason(StrEnum):
    """Closed set of reasons a component reached its current state.

    Keeping reasons enumerated (instead of free text) is what stops caption
    text, credentials or raw SDK messages from ever reaching a status payload.
    """

    START = "start"
    STOP = "stop"
    TIMER = "timer"
    GOAWAY = "goaway"
    ERROR = "error"
    PARTIAL = "partial"
    FINAL = "final"
    RESET = "reset"


class Component(StrEnum):
    """Runtime components a user can observe."""

    AUDIO_SOURCE = "audio_source"
    GEMINI_PROVIDER = "gemini_provider"
    GEMINI_SESSION = "gemini_session"
    CAPTION_SINK = "caption_sink"
    VMIX_OUTPUT = "vmix_output"


class ComponentState(StrEnum):
    """States a component can report.

    The set is shared across components; ``_ALLOWED_STATES`` keeps each
    component to the states that are meaningful for it, so an unmapped
    combination fails closed instead of surfacing a nonsensical UI state.
    """

    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ACTIVE = "active"
    ROTATING = "rotating"
    BACKOFF = "backoff"
    FAIL_CLOSED = "fail_closed"
    RESET = "reset"
    ERROR = "error"


_SHARED_STATES = frozenset({ComponentState.IDLE, ComponentState.ERROR})

_ALLOWED_STATES: dict[Component, frozenset[ComponentState]] = {
    Component.AUDIO_SOURCE: _SHARED_STATES
    | {
        ComponentState.STARTING,
        ComponentState.RUNNING,
        ComponentState.STOPPING,
        ComponentState.STOPPED,
    },
    Component.GEMINI_PROVIDER: _SHARED_STATES
    | {
        ComponentState.CONNECTING,
        ComponentState.CONNECTED,
        ComponentState.BACKOFF,
        ComponentState.FAIL_CLOSED,
        ComponentState.STOPPED,
    },
    Component.GEMINI_SESSION: _SHARED_STATES
    | {
        ComponentState.ACTIVE,
        ComponentState.ROTATING,
        ComponentState.STOPPED,
    },
    Component.CAPTION_SINK: _SHARED_STATES
    | {
        ComponentState.ACTIVE,
        ComponentState.RESET,
    },
    # `idle` here means the output is switched off, which is the normal state
    # for anyone not using vMix — it must not read as a fault.
    Component.VMIX_OUTPUT: _SHARED_STATES
    | {
        ComponentState.CONNECTING,
        ComponentState.CONNECTED,
        ComponentState.ACTIVE,
        ComponentState.BACKOFF,
        ComponentState.STOPPED,
    },
}


@dataclass(frozen=True)
class ComponentStatus:
    """An immutable, metadata-only status snapshot for one component.

    ``detail`` is composed by :class:`~backend.app.status.publisher.StatusPublisher`
    from whitelisted metadata fields; it never carries caption text, credentials
    or raw SDK error content.
    """

    component: Component
    state: ComponentState
    updated_at: float
    detail: str | None = None
    revision: int = 0
    session_generation: int | None = None

    def __post_init__(self) -> None:
        allowed = _ALLOWED_STATES[self.component]
        if self.state not in allowed:
            raise StatusError(
                f"元件 {self.component.value} 不支援狀態 {self.state.value}。"
            )
        if self.revision < 0:
            raise StatusError("status revision 不得為負數。")
        if self.session_generation is not None and self.session_generation < 0:
            raise StatusError("session generation 不得為負數。")

    @classmethod
    def idle(cls, component: Component) -> ComponentStatus:
        return cls(component=component, state=ComponentState.IDLE, updated_at=0.0)


@dataclass(frozen=True)
class RuntimeStatusSnapshot:
    """Immutable view of every component status at one store revision."""

    revision: int
    statuses: tuple[ComponentStatus, ...] = field(default_factory=tuple)

    def by_component(self, component: Component) -> ComponentStatus | None:
        for status in self.statuses:
            if status.component is component:
                return status
        return None
