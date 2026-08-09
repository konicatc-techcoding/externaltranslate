from __future__ import annotations

import pytest

from backend.app.captions.models import CaptionState, CaptionStatus
from backend.app.captions.store import CaptionStore, CaptionStoreError


def _state(
    revision: int,
    text: str = "你好",
    status: CaptionStatus = CaptionStatus.PARTIAL,
) -> CaptionState:
    return CaptionState(
        revision=revision,
        status=status,
        text=text,
        language_code="zh-Hant",
        updated_at=float(revision),
        session_generation=1,
    )


def test_store_starts_idle() -> None:
    store = CaptionStore()
    state = store.snapshot()
    assert state.status is CaptionStatus.IDLE
    assert state.revision == 0


def test_store_commit_then_snapshot_returns_latest() -> None:
    store = CaptionStore()
    store.commit(_state(revision=1, text="你"))
    store.commit(_state(revision=2, text="你好"))
    assert store.snapshot().text == "你好"
    assert store.snapshot().revision == 2


def test_store_rejects_revision_regression() -> None:
    store = CaptionStore()
    store.commit(_state(revision=2))
    with pytest.raises(CaptionStoreError, match="倒退|降低|revision"):
        store.commit(_state(revision=1))


def test_store_accepts_same_revision() -> None:
    store = CaptionStore()
    store.commit(_state(revision=2, text="a"))
    store.commit(_state(revision=2, text="b"))
    assert store.snapshot().text == "b"


def test_store_rejects_updated_at_regression() -> None:
    store = CaptionStore()
    store.commit(_state(revision=2))
    regressed = CaptionState(
        revision=3,
        status=CaptionStatus.PARTIAL,
        text="x",
        language_code="zh-Hant",
        updated_at=1.0,  # lower than previous 2.0
        session_generation=1,
    )
    with pytest.raises(CaptionStoreError):
        store.commit(regressed)


def test_store_reset_returns_to_idle() -> None:
    store = CaptionStore()
    store.commit(_state(revision=5))
    store.reset()
    assert store.snapshot().status is CaptionStatus.IDLE
    assert store.snapshot().revision == 0