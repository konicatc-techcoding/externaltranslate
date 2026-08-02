from __future__ import annotations

from collections import deque
from threading import Condition
from typing import Generic, TypeVar

T = TypeVar("T")


class DroppingQueue(Generic[T]):
    """Bounded handoff that drops the oldest item instead of adding latency."""

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity 必須大於 0。")
        self._capacity = capacity
        self._items: deque[T] = deque()
        self._condition = Condition()
        self._dropped_count = 0

    @property
    def dropped_count(self) -> int:
        with self._condition:
            return self._dropped_count

    @property
    def size(self) -> int:
        with self._condition:
            return len(self._items)

    def put_nowait(self, item: T) -> bool:
        with self._condition:
            dropped = len(self._items) >= self._capacity
            if dropped:
                self._items.popleft()
                self._dropped_count += 1
            self._items.append(item)
            self._condition.notify()
            return dropped

    def get_nowait(self) -> T:
        with self._condition:
            if not self._items:
                raise TimeoutError("佇列目前沒有資料。")
            return self._items.popleft()

    def get(self, timeout: float) -> T:
        if timeout < 0:
            raise ValueError("timeout 不得小於 0。")
        with self._condition:
            available = self._condition.wait_for(lambda: bool(self._items), timeout)
            if not available:
                raise TimeoutError("等待佇列資料逾時。")
            return self._items.popleft()

    def clear(self) -> int:
        with self._condition:
            removed = len(self._items)
            self._items.clear()
            return removed
