from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from contextlib import suppress
from enum import StrEnum

from backend.app.outputs.sender import ThrottledSender
from backend.app.outputs.vmix import VmixClient, VmixError


class OutputState(StrEnum):
    """What the output is doing, in terms this package can express.

    Deliberately not `ComponentState`: the status package stays a consumer of
    outputs, not a dependency of it, the same way captions do not import it.
    """

    CONNECTED = "connected"
    ACTIVE = "active"
    BACKOFF = "backoff"
    ERROR = "error"
    STOPPED = "stopped"


OnState = Callable[[OutputState], None]

# vMix expects Windows line endings inside a single text field.
_JOIN = "\r\n"


class VmixOutput:
    """Writes caption lines into a vMix GT Title's text fields.

    One line per field by default: a GT Title gives no wrapping guarantee, so
    the backend's own line breaks are the only way the title and the web
    overlay can agree on where a line ends.

    Every failure stays inside this class. `publish` returns immediately and
    never raises, because it is called from the caption path — translation
    must not stop because a title did not update.
    """

    def __init__(
        self,
        client: VmixClient,
        *,
        input_guid: str,
        fields: Sequence[str],
        min_interval_ms: int,
        on_state: OnState | None = None,
    ) -> None:
        self._client = client
        self._input_guid = input_guid
        self._fields = tuple(fields)
        self._single_field_join = False
        self._on_state = on_state
        self._state: OutputState | None = None
        self._sender = ThrottledSender(
            self._deliver,
            min_interval_ms=min_interval_ms,
            on_result=self._on_delivery,
        )
        self._task: asyncio.Task[None] | None = None
        self._last_error: str | None = None

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def failures(self) -> int:
        return self._sender.failures

    @property
    def field_count(self) -> int:
        return len(self._fields)

    def set_single_field_join(self, enabled: bool) -> None:
        """Join all lines into the first field with CRLF instead of one each.

        Whether that renders as multiple lines is a property of the operator's
        title, not something this program can promise.
        """
        self._single_field_join = enabled

    async def start(self) -> bool:
        """Verify the input still exists, then begin sending.

        Returns False when the target is gone. The GUID is checked rather than
        assumed because a title deleted or replaced in vMix would otherwise
        swallow every update with no visible sign.
        """
        try:
            inputs = await self._client.inputs()
        except VmixError as exc:
            self._last_error = str(exc)
            self._publish_state(OutputState.ERROR)
            return False

        if not any(item.guid == self._input_guid for item in inputs):
            self._last_error = (
                "在 vMix 找不到設定的 input；請重新選擇要輸出的 GT Title。"
            )
            self._publish_state(OutputState.ERROR)
            return False

        self._last_error = None
        self._publish_state(OutputState.CONNECTED)
        self._sender.forget_last_sent()
        self._task = asyncio.create_task(self._sender.run(), name="vmix-output")
        return True

    def publish(self, lines: Sequence[str]) -> None:
        self._sender.submit(self._to_field_values(lines))

    async def clear(self) -> None:
        self._sender.submit(tuple("" for _ in self._fields))
        await self._sender.flush()

    async def aclose(self) -> None:
        await self._sender.aclose()
        self._publish_state(OutputState.STOPPED)
        task = self._task
        self._task = None
        if task is not None:
            with suppress(asyncio.CancelledError):
                await task

    def _on_delivery(self, delivered: bool) -> None:
        # Only transitions are published: a status event per caption fragment
        # would bury every other component in the feed.
        self._publish_state(OutputState.ACTIVE if delivered else OutputState.BACKOFF)

    def _publish_state(self, state: OutputState) -> None:
        if state is self._state:
            return
        self._state = state
        if self._on_state is not None:
            self._on_state(state)

    def _to_field_values(self, lines: Sequence[str]) -> tuple[str, ...]:
        if self._single_field_join and self._fields:
            joined = _JOIN.join(lines)
            return (joined,) + tuple("" for _ in self._fields[1:])
        # Keep the newest lines when the title has fewer fields than the
        # caption has lines, matching the sliding window everywhere else.
        visible = list(lines)[-len(self._fields) :] if self._fields else []
        padded = visible + [""] * (len(self._fields) - len(visible))
        return tuple(padded)

    async def _deliver(self, values: tuple[str, ...]) -> None:
        for field, value in zip(self._fields, values, strict=False):
            try:
                await self._client.set_text(self._input_guid, field, value)
            except VmixError as exc:
                self._last_error = str(exc)
                raise
        self._last_error = None
