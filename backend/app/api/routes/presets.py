from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.api.dependencies import get_runtime
from backend.app.api.models import (
    CaptionPresetItem,
    CaptionPresetList,
    CaptionPresetSave,
    MessageResponse,
)
from backend.app.captions.presets import CaptionPreset, PresetError
from backend.app.services.runtime import PipelineRuntime

router = APIRouter(prefix="/api/caption-presets", tags=["presets"])


def _to_item(preset: CaptionPreset) -> CaptionPresetItem:
    return CaptionPresetItem(**asdict(preset))


@router.get("", response_model=CaptionPresetList)
def list_presets(
    runtime: Annotated[PipelineRuntime, Depends(get_runtime)],
) -> CaptionPresetList:
    return CaptionPresetList(
        presets=[_to_item(preset) for preset in runtime.presets.list()]
    )


@router.put("", response_model=CaptionPresetList)
def save_preset(
    payload: CaptionPresetSave,
    runtime: Annotated[PipelineRuntime, Depends(get_runtime)],
) -> CaptionPresetList:
    """Save the settings currently in force under a name."""
    try:
        runtime.presets.save(runtime.current_preset(payload.name))
    except PresetError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from None
    return list_presets(runtime)


@router.post("/{name}/apply", response_model=MessageResponse)
def apply_preset(
    name: str,
    runtime: Annotated[PipelineRuntime, Depends(get_runtime)],
) -> MessageResponse:
    try:
        runtime.apply_preset(runtime.presets.get(name))
    except PresetError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from None
    return MessageResponse(message=f"已套用字幕預設「{name}」。")


@router.delete("/{name}", response_model=CaptionPresetList)
def delete_preset(
    name: str,
    runtime: Annotated[PipelineRuntime, Depends(get_runtime)],
) -> CaptionPresetList:
    try:
        runtime.presets.delete(name)
    except PresetError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from None
    return list_presets(runtime)
