from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class PrerequisiteStatus(StrEnum):
    """Normalized state shown by setup diagnostics."""

    READY = "ready"
    MISSING = "missing"
    NOT_REQUIRED = "not_required"
    OPTIONAL = "optional"
    NOT_CHECKED = "not_checked"


@dataclass(frozen=True)
class PrerequisiteResult:
    """One prerequisite result with a user-facing Traditional Chinese action."""

    identifier: str
    label: str
    status: PrerequisiteStatus
    required_for: str
    version: str | None = None
    detail: str = ""
    action: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data
