from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.api.dependencies import get_runtime
from backend.app.api.models import (
    MessageResponse,
    VmixInputItem,
    VmixInputList,
    VmixTestRequest,
)
from backend.app.config import vmix_settings
from backend.app.outputs.vmix import VmixError
from backend.app.services.runtime import PipelineRuntime

router = APIRouter(prefix="/api/vmix", tags=["vmix"])


@router.get("/inputs", response_model=VmixInputList)
async def read_inputs(
    runtime: Annotated[PipelineRuntime, Depends(get_runtime)],
) -> VmixInputList:
    """List vMix inputs so the operator can pick one by name.

    The GUID is what gets stored; the name is only how a human recognises it.
    """
    try:
        inputs = await runtime.vmix_client().inputs()
    except VmixError as exc:
        # vMix not running is the ordinary case, so this is "unavailable",
        # not a client mistake.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from None
    return VmixInputList(
        inputs=[
            VmixInputItem(
                guid=item.guid,
                number=item.number,
                name=item.name,
                kind=item.kind,
                text_fields=list(item.text_fields),
            )
            for item in inputs
        ]
    )


@router.post("/test", response_model=MessageResponse)
async def send_test_text(
    payload: VmixTestRequest,
    runtime: Annotated[PipelineRuntime, Depends(get_runtime)],
) -> MessageResponse:
    """Write one line into the configured title, to prove the wiring works."""
    vmix = vmix_settings(runtime.settings)
    guid = vmix["input_guid"]
    if not guid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="尚未選擇要輸出的 vMix input。",
        )
    fields = list(vmix["fields"])
    try:
        await runtime.vmix_client().set_text(str(guid), fields[0], payload.text)
    except VmixError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from None
    return MessageResponse(
        message=f"已送出測試文字到「{vmix['input_name'] or guid}」的 {fields[0]}。"
    )
