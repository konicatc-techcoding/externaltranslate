from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence

Deliver = Callable[[tuple[str, ...]], Awaitable[None]]
Sleep = Callable[[float], Awaitable[None]]
OnResult = Callable[[bool], None]

# Same shape as the Gemini supervisor: bounded, growing, never a tight loop.
_BACKOFF_SECONDS = (0.5, 1.0, 2.0, 4.0, 5.0)


class ThrottledSender:
    """Sends the newest caption state, at most once per interval.

    Captions update several times a second and only the newest one has any
    display value, so intermediate states are coalesced rather than queued.

    The one behaviour worth stating outright: **the last state always goes
    out**. A throttle that merely drops updates arriving too fast leaves the
    caption permanently one fragment behind — the speaker stops, and the
    screen keeps showing the second-to-last thing they said.

    `submit` never blocks and never raises: it runs on the caption path, and
    a failure to reach vMix must not disturb translation.
    """

    def __init__(
        self,
        deliver: Deliver,
        *,
        min_interval_ms: int,
        sleep: Sleep | None = None,
        on_result: OnResult | None = None,
    ) -> None:
        self._deliver = deliver
        self._on_result = on_result
        self._min_interval = min_interval_ms / 1000
        self._sleep = sleep or asyncio.sleep
        self._pending: tuple[str, ...] | None = None
        self._last_sent: tuple[str, ...] | None = None
        self._wakeup = asyncio.Event()
        self._closed = False
        self._failures = 0

    @property
    def failures(self) -> int:
        """Consecutive delivery failures; zero once a send succeeds."""
        return self._failures

    def submit(self, lines: Sequence[str]) -> None:
        if self._closed:
            return
        self._pending = tuple(lines)
        self._wakeup.set()

    def forget_last_sent(self) -> None:
        """Drop the dedup memory so the next submit is sent even if identical.

        Needed after the connection or the target input changes: what vMix is
        showing is no longer what we think we sent.
        """
        self._last_sent = None

    def _notify(self, delivered: bool) -> None:
        if self._on_result is None:
            return
        # Never let an observer's mistake break delivery.
        try:
            self._on_result(delivered)
        except Exception:
            return

    async def flush(self) -> None:
        """Deliver whatever is pending right now, ignoring the throttle.

        Used for the blank-the-fields write when translation stops: that one
        must not wait behind an interval, and it must not be lost to the
        shutdown. A failure here is swallowed — vMix being already gone is not
        a reason to hold up stopping.
        """
        payload = self._pending
        self._pending = None
        if payload is None or payload == self._last_sent:
            return
        try:
            await self._deliver(payload)
        except Exception:
            return
        self._last_sent = payload

    async def aclose(self) -> None:
        self._closed = True
        self._wakeup.set()

    async def run(self) -> None:
        while not self._closed:
            await self._wakeup.wait()
            self._wakeup.clear()
            if self._closed:
                return

            payload = self._pending
            self._pending = None
            if payload is None or payload == self._last_sent:
                continue

            try:
                await self._deliver(payload)
            except Exception:
                self._notify(False)
                # Keep the state so it still lands once vMix comes back, but
                # never overwrite something newer that arrived meanwhile.
                self._failures += 1
                if self._pending is None:
                    self._pending = payload
                self._wakeup.set()
                await self._sleep(
                    _BACKOFF_SECONDS[min(self._failures - 1, len(_BACKOFF_SECONDS) - 1)]
                )
                continue

            self._last_sent = payload
            self._failures = 0
            self._notify(True)
            # Throttle *after* delivering: anything submitted during this wait
            # is coalesced and goes out as soon as the window closes.
            await self._sleep(self._min_interval)
