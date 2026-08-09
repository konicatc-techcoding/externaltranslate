from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.api.dependencies import get_runtime
from backend.app.api.serializers import runtime_status_response
from backend.app.services.runtime import PipelineRuntime, RuntimeSnapshot

router = APIRouter(tags=["websocket"])

DEFAULT_POLL_INTERVAL = 0.1


def _push_key(snapshot: RuntimeSnapshot) -> tuple[int, int, bool, str | None]:
    """What counts as a change worth sending.

    Caption revision alone is not enough: a session boundary that retains a
    confirmed final deliberately keeps the revision and only moves
    ``updated_at``, so status revision and running state are part of the key.
    """
    return (
        snapshot.caption.revision,
        snapshot.status.revision,
        snapshot.running,
        snapshot.last_error,
    )


@router.websocket("/ws/captions")
async def caption_socket(websocket: WebSocket) -> None:
    runtime: PipelineRuntime = websocket.app.state.runtime
    interval: float = getattr(
        websocket.app.state, "ws_poll_interval", DEFAULT_POLL_INTERVAL
    )
    await websocket.accept()

    snapshot = runtime.snapshot()
    last_key = _push_key(snapshot)
    try:
        # A freshly opened overlay must never wait for the next change.
        await websocket.send_json(runtime_status_response(snapshot).model_dump())
        while True:
            await asyncio.sleep(interval)
            snapshot = runtime.snapshot()
            key = _push_key(snapshot)
            if key == last_key:
                continue
            last_key = key
            await websocket.send_json(runtime_status_response(snapshot).model_dump())
    except WebSocketDisconnect:
        return
    except RuntimeError:
        # Socket closed underneath us while sending; nothing to clean up.
        return


__all__ = ["router", "get_runtime", "DEFAULT_POLL_INTERVAL"]
