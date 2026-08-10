from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from backend.app.status.models import (
    Component,
    ComponentState,
    ComponentStatus,
    StatusError,
    StatusReason,
)
from backend.app.status.store import StatusStore

STATUS_LOGGER_NAME = "externaltranslate.status"

_Now = Callable[[], float]
_Sink = Callable[[ComponentStatus], None]

# Ordered whitelist: only these metadata fields may appear in a status detail.
# Anything else — caption text, credentials, device identifiers, SDK error
# strings — is rejected before it can reach the store, the log or the CLI.
_FIELD_ORDER = (
    "generation",
    "reason",
    "attempt",
    "delay_seconds",
    "rotation_seconds",
    "text_length",
    # vMix: how many title fields were written. A count, never the content.
    "field_count",
)


def _coerce_non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise StatusError(f"status 欄位 {name} 必須是整數。")
    if value < 0:
        raise StatusError(f"status 欄位 {name} 不得為負數。")
    return value


def _coerce_seconds(name: str, value: object, *, positive: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise StatusError(f"status 欄位 {name} 必須是秒數。")
    seconds = float(value)
    if positive and seconds <= 0:
        raise StatusError(f"status 欄位 {name} 必須大於 0。")
    if not positive and seconds < 0:
        raise StatusError(f"status 欄位 {name} 不得為負數。")
    return seconds


def _coerce_reason(value: object) -> StatusReason:
    if isinstance(value, StatusReason):
        return value
    if isinstance(value, str):
        try:
            return StatusReason(value)
        except ValueError as exc:
            raise StatusError("status 欄位 reason 必須是已定義的原因代碼。") from exc
    raise StatusError("status 欄位 reason 必須是已定義的原因代碼。")


def _validate_fields(fields: dict[str, Any]) -> dict[str, Any]:
    unknown = set(fields) - set(_FIELD_ORDER)
    if unknown:
        field = sorted(unknown)[0]
        raise StatusError(f"不支援或可能洩漏內容的 status 欄位：{field}")
    validated: dict[str, Any] = {}
    for name, value in fields.items():
        if name in ("generation", "attempt", "text_length", "field_count"):
            validated[name] = _coerce_non_negative_int(name, value)
        elif name == "delay_seconds":
            validated[name] = _coerce_seconds(name, value, positive=False)
        elif name == "rotation_seconds":
            validated[name] = _coerce_seconds(name, value, positive=True)
        else:
            validated[name] = _coerce_reason(value)
    return validated


def _compose_detail(fields: dict[str, Any]) -> str | None:
    parts = [
        f"{name}={fields[name].value if name == 'reason' else fields[name]}"
        for name in _FIELD_ORDER
        if name in fields
    ]
    return " ".join(parts) if parts else None


def status_payload(status: ComponentStatus) -> dict[str, Any]:
    """Return a JSON-safe, metadata-only payload for CLI or WebSocket output."""
    return {
        "status": "component",
        "component": status.component.value,
        "state": status.state.value,
        "detail": status.detail,
        "revision": status.revision,
        "session_generation": status.session_generation,
        "updated_at": status.updated_at,
    }


class StatusPublisher:
    """Publish component status transitions to a store, a log and a sink.

    Callers pass only whitelisted metadata keyword fields; the human-readable
    ``detail`` is composed here, so no caller can smuggle transcript text or a
    credential into an observable surface.
    """

    def __init__(
        self,
        store: StatusStore,
        *,
        logger: logging.Logger | None = None,
        now: _Now | None = None,
        sink: _Sink | None = None,
    ) -> None:
        self._store = store
        self._logger = logger or logging.getLogger(STATUS_LOGGER_NAME)
        self._now = now or time.monotonic
        self._sink = sink

    def publish(
        self,
        component: Component,
        state: ComponentState,
        **fields: Any,
    ) -> ComponentStatus:
        validated = _validate_fields(fields)
        generation = validated.get("generation")
        status = ComponentStatus(
            component=component,
            state=state,
            updated_at=self._now(),
            detail=_compose_detail(validated),
            session_generation=generation,
        )
        stamped = self._store.update(status)
        self._logger.info(
            "component=%s state=%s revision=%s detail=%s",
            stamped.component.value,
            stamped.state.value,
            stamped.revision,
            stamped.detail or "-",
        )
        if self._sink is not None:
            self._sink(stamped)
        return stamped
