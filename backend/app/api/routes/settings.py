from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.api.dependencies import get_runtime
from backend.app.api.models import SettingsResponse, SettingsUpdate
from backend.app.config import caption_max_payload_length
from backend.app.services.runtime import (
    PipelineRuntime,
    RuntimeConflictError,
    RuntimeSelectionError,
)

router = APIRouter(prefix="/api", tags=["settings"])


def _to_response(settings: Any) -> SettingsResponse:
    audio = settings["audio"]
    gemini = settings["gemini"]
    return SettingsResponse(
        source_kind=audio["source_kind"],
        device_index=audio["device_index"],
        loopback_endpoint_index=audio["loopback_endpoint_index"],
        channel=audio["channel"],
        caption_max_payload_length=caption_max_payload_length(settings),
        session_rotation_seconds=gemini["session_rotation_seconds"],
    )


@router.get("/settings", response_model=SettingsResponse)
def read_settings(
    runtime: Annotated[PipelineRuntime, Depends(get_runtime)],
) -> SettingsResponse:
    return _to_response(runtime.settings)


@router.put("/settings", response_model=SettingsResponse)
def update_settings(
    payload: SettingsUpdate,
    runtime: Annotated[PipelineRuntime, Depends(get_runtime)],
) -> SettingsResponse:
    try:
        runtime.update_audio_selection(
            source_kind=payload.source_kind,
            device_index=payload.device_index,
            endpoint_index=payload.loopback_endpoint_index,
            channel=payload.channel,
        )
    except RuntimeConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from None
    except RuntimeSelectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from None
    return _to_response(runtime.settings)
