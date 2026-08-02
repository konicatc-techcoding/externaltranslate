from __future__ import annotations

import pytest

from backend.app.audio.queue import DroppingQueue


def test_queue_drops_oldest_item_when_capacity_is_reached() -> None:
    queue = DroppingQueue[str](capacity=2)

    assert queue.put_nowait("first") is False
    assert queue.put_nowait("second") is False
    assert queue.put_nowait("third") is True

    assert queue.dropped_count == 1
    assert queue.get_nowait() == "second"
    assert queue.get_nowait() == "third"


def test_queue_reports_empty_without_blocking() -> None:
    queue = DroppingQueue[bytes](capacity=1)

    with pytest.raises(TimeoutError, match="佇列目前沒有資料"):
        queue.get_nowait()


def test_queue_rejects_non_positive_capacity() -> None:
    with pytest.raises(ValueError, match="capacity"):
        DroppingQueue[int](capacity=0)
