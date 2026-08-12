from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.api.dependencies import get_runtime
from backend.app.api.models import (
    ManualCaptionRequest,
    ManualCaptionResponse,
    VmixInputItem,
    VmixInputList,
    VmixTestRequest,
    VmixTestResponse,
)
from backend.app.outputs.vmix import VmixError
from backend.app.services.runtime import (
    PipelineRuntime,
    RuntimeConflictError,
    RuntimeSelectionError,
)

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


@router.post("/test", response_model=VmixTestResponse)
async def send_test_caption(
    payload: VmixTestRequest,
    runtime: Annotated[PipelineRuntime, Depends(get_runtime)],
) -> VmixTestResponse:
    """Write a full set of lines, one per field, through the real output path.

    Every field is written — including blanking the ones a shorter caption
    would not fill — so the test shows the same thing a running translation
    would, in the same order.
    """
    try:
        written = await runtime.send_vmix_test(payload.lines)
    except RuntimeConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from None
    except RuntimeSelectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from None
    except VmixError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from None
    return VmixTestResponse(
        message=f"已送出 {len(written)} 行測試字幕；請比對 vMix 畫面的順序。",
        lines=written,
    )


@router.post("/clear", response_model=VmixTestResponse)
async def clear_fields(
    runtime: Annotated[PipelineRuntime, Depends(get_runtime)],
) -> VmixTestResponse:
    """Blank every configured field, for tidying up after a test."""
    try:
        await runtime.clear_vmix_fields()
    except RuntimeConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from None
    except RuntimeSelectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from None
    except VmixError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from None
    return VmixTestResponse(message="已清空 vMix 字幕欄位。", lines=[])


@router.post("/manual", response_model=ManualCaptionResponse)
async def send_manual_caption(
    payload: ManualCaptionRequest,
    runtime: Annotated[PipelineRuntime, Depends(get_runtime)],
) -> ManualCaptionResponse:
    """Put typed text on the manual title, replacing whatever is there.

    Allowed while translating, unlike the test caption: this writes to a
    different input, so there is nothing for the running translation to
    overwrite and nothing here that would disturb it.
    """
    try:
        lines = await runtime.send_manual_caption(payload.text)
    except RuntimeSelectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from None
    except VmixError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from None
    return ManualCaptionResponse(
        message="已送出手動字幕。",
        lines=lines,
        overflowed=runtime.manual_overflowed,
    )


@router.post("/manual/clear", response_model=ManualCaptionResponse)
async def clear_manual_caption(
    runtime: Annotated[PipelineRuntime, Depends(get_runtime)],
) -> ManualCaptionResponse:
    try:
        await runtime.clear_manual_caption()
    except RuntimeSelectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from None
    except VmixError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from None
    return ManualCaptionResponse(message="已清空手動字幕。", lines=[], overflowed=False)
