from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.api.dependencies import get_runtime
from backend.app.api.models import (
    CaptionLayoutUpdate,
    CaptionStyle,
    CaptionStyleUpdate,
    SettingsResponse,
    SettingsUpdate,
    UiSettings,
    VmixSettings,
    VmixSettingsUpdate,
)
from backend.app.config import (
    caption_idle_reset_ms,
    caption_layout,
    caption_max_payload_length,
    caption_sentence_breaks,
    caption_style,
    ui_settings,
    vmix_settings,
)
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
        caption_chars_per_line=caption_layout(settings)[0],
        caption_max_lines=caption_layout(settings)[1],
        caption_sentence_breaks=caption_sentence_breaks(settings),
        caption_idle_reset_ms=caption_idle_reset_ms(settings),
        caption_style=CaptionStyle(**caption_style(settings)),
        vmix=VmixSettings(**vmix_settings(settings)),
        ui=UiSettings(**ui_settings(settings)),
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


@router.put("/settings/caption-layout", response_model=SettingsResponse)
def update_caption_layout(
    payload: CaptionLayoutUpdate,
    runtime: Annotated[PipelineRuntime, Depends(get_runtime)],
) -> SettingsResponse:
    """Change the caption layout, allowed while translating."""
    try:
        runtime.update_caption_layout(
            chars_per_line=payload.chars_per_line,
            max_lines=payload.max_lines,
            sentence_breaks=payload.sentence_breaks,
            idle_reset_ms=payload.idle_reset_ms,
        )
    except RuntimeSelectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from None
    return _to_response(runtime.settings)


@router.put("/settings/caption-style", response_model=SettingsResponse)
def update_caption_style(
    payload: CaptionStyleUpdate,
    runtime: Annotated[PipelineRuntime, Depends(get_runtime)],
) -> SettingsResponse:
    """Change overlay appearance, allowed while translating."""
    try:
        runtime.update_caption_style(payload.model_dump())
    except RuntimeSelectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from None
    return _to_response(runtime.settings)


@router.put("/settings/vmix", response_model=SettingsResponse)
async def update_vmix(
    payload: VmixSettingsUpdate,
    runtime: Annotated[PipelineRuntime, Depends(get_runtime)],
) -> SettingsResponse:
    """Change the vMix target. Applies on the next start, not mid-run.

    Retargeting a live output would leave the previous title showing whatever
    was on it, with nothing left to clear it. `enabled` is the exception and
    applies immediately — see `PipelineRuntime.set_vmix_enabled`.
    """
    # `exclude_unset`, not `exclude_none`: the panel clears the chosen input by
    # sending an explicit null, and `exclude_none` would drop it silently —
    # the "—" option would appear to do nothing.
    changes = payload.model_dump(exclude_unset=True)
    enabled = changes.pop("enabled", None)
    try:
        if changes:
            runtime.update_vmix_settings(changes)
        if enabled is not None:
            await runtime.set_vmix_enabled(bool(enabled))
    except RuntimeSelectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from None
    return _to_response(runtime.settings)


@router.put("/settings/ui", response_model=SettingsResponse)
def update_ui(
    payload: UiSettings,
    runtime: Annotated[PipelineRuntime, Depends(get_runtime)],
) -> SettingsResponse:
    """Remember which panels are folded away, so a reload keeps the layout."""
    try:
        runtime.update_collapsed_panels(payload.collapsed)
    except RuntimeSelectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from None
    return _to_response(runtime.settings)
