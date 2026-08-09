from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.api.dependencies import get_runtime
from backend.app.api.models import MessageResponse, RuntimeStatusResponse
from backend.app.api.serializers import runtime_status_response
from backend.app.services.runtime import (
    PipelineRuntime,
    RuntimeConflictError,
    RuntimeCredentialError,
    RuntimeSelectionError,
)

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.post("/start", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_pipeline(
    runtime: Annotated[PipelineRuntime, Depends(get_runtime)],
) -> MessageResponse:
    try:
        await runtime.start()
    except RuntimeCredentialError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from None
    except RuntimeConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from None
    except RuntimeSelectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from None
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="無法啟動翻譯；請確認音訊裝置與設定後再試。",
        ) from None
    return MessageResponse(message="翻譯已開始。")


@router.post("/stop", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
async def stop_pipeline(
    runtime: Annotated[PipelineRuntime, Depends(get_runtime)],
) -> MessageResponse:
    await runtime.stop()
    return MessageResponse(message="翻譯已停止。")


@router.get("/status", response_model=RuntimeStatusResponse)
def read_status(
    runtime: Annotated[PipelineRuntime, Depends(get_runtime)],
) -> RuntimeStatusResponse:
    return runtime_status_response(runtime.snapshot())
