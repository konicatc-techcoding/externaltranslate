from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.api.dependencies import get_runtime
from backend.app.api.serializers import runtime_status_response
from backend.app.services.runtime import PipelineRuntime, RuntimeSnapshot

router = APIRouter(tags=["websocket"])

DEFAULT_POLL_INTERVAL = 0.1


def _push_key(snapshot: RuntimeSnapshot) -> tuple[Any, ...]:
    """What counts as a change worth sending.

    Everything the payload can show has to be in here. Caption revision alone
    is not enough: a session boundary that retains a confirmed final keeps the
    revision and only moves ``updated_at``, and an appearance change reflows
    nothing at all — without layout and style in the key, changing the font
    would never reach the pages showing it.
    """
    return (
        snapshot.caption.revision,
        snapshot.status.revision,
        snapshot.running,
        snapshot.last_error,
        snapshot.layout,
        snapshot.sentence_breaks,
        tuple(sorted(snapshot.style.items())),
        snapshot.audio_notice,
    )


_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}


def is_allowed_origin(origin: str | None) -> bool:
    """Allow only loopback pages to open the caption socket.

    Browsers do not apply the same-origin policy to WebSocket, so without this
    any site the user visits could connect to the local service and read the
    captions. A missing Origin means a non-browser client (CLI, tests).
    """
    if origin is None:
        return True
    scheme, separator, rest = origin.partition("://")
    if not separator or scheme not in {"http", "https"}:
        return False
    host = rest.split("/", 1)[0]
    hostname = host.rsplit(":", 1)[0] if ":" in host and not host.endswith("]") else host
    return hostname in _LOOPBACK_HOSTS


async def _drain(websocket: WebSocket) -> None:
    """Read and discard client frames until the socket goes away.

    This is a push-only channel, but the socket still has to be read: without
    it a client that navigates away is only noticed on the next send, so an
    idle connection would leave a task writing to a dead socket.
    """
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return


@router.websocket("/ws/captions")
async def caption_socket(websocket: WebSocket) -> None:
    runtime: PipelineRuntime = websocket.app.state.runtime
    interval: float = getattr(
        websocket.app.state, "ws_poll_interval", DEFAULT_POLL_INTERVAL
    )
    if not is_allowed_origin(websocket.headers.get("origin")):
        await websocket.close(code=1008)
        return
    await websocket.accept()

    receiver = asyncio.create_task(_drain(websocket), name="caption-socket-reader")
    try:
        snapshot = runtime.snapshot()
        last_key = _push_key(snapshot)
        # A freshly opened overlay must never wait for the next change.
        await websocket.send_json(runtime_status_response(snapshot).model_dump())

        while not receiver.done():
            # Waking on the reader means a disconnect ends the loop at once
            # instead of one poll interval later.
            await asyncio.wait({receiver}, timeout=interval)
            if receiver.done():
                break
            snapshot = runtime.snapshot()
            key = _push_key(snapshot)
            if key == last_key:
                continue
            last_key = key
            await websocket.send_json(runtime_status_response(snapshot).model_dump())
    except (WebSocketDisconnect, RuntimeError):
        # Socket closed underneath us; nothing to clean up but the reader.
        pass
    finally:
        receiver.cancel()
        with suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
            await receiver


__all__ = ["router", "get_runtime", "DEFAULT_POLL_INTERVAL"]
