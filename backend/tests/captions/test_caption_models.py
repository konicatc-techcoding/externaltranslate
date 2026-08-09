from __future__ import annotations

import dataclasses

import pytest

from backend.app.captions.models import CaptionState, CaptionStatus


def test_caption_state_is_frozen_and_has_required_fields() -> None:
    state = CaptionState(
        revision=3,
        status=CaptionStatus.PARTIAL,
        text="你好",
        language_code="zh-Hant",
        updated_at=1234567.0,
        session_generation=1,
    )
    assert dataclasses.is_dataclass(state)
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.text = "x"  # type: ignore[misc]
    assert state.revision == 3
    assert state.status is CaptionStatus.PARTIAL
    assert state.language_code == "zh-Hant"
    assert state.session_generation == 1


def test_caption_status_enum_values() -> None:
    assert [item.value for item in CaptionStatus] == ["idle", "partial", "final"]


def test_caption_state_initial_factory() -> None:
    state = CaptionState.initial()
    assert state.revision == 0
    assert state.status is CaptionStatus.IDLE
    assert state.text == ""
    assert state.language_code == ""
    assert state.session_generation == 0