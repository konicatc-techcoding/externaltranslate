from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

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


shutdown_router = APIRouter(prefix="/api", tags=["pipeline"])


@shutdown_router.post("/shutdown", response_model=MessageResponse)
async def shutdown(
    request: Request,
    runtime: Annotated[PipelineRuntime, Depends(get_runtime)],
) -> MessageResponse:
    """Stop translating and end the process.

    Translation is stopped first and awaited: that path is what blanks the vMix
    title, and a process that exits without it leaves the last sentence frozen
    on air with nothing left able to clear it.

    The exit itself is only *requested*. Performing it here would kill the
    server before this reply left the socket, and the page would show a failed
    request instead of saying it closed.
    """
    request_shutdown = getattr(request.app.state, "request_shutdown", None)
    if request_shutdown is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="這個執行方式不支援從網頁關閉程式；請直接關閉服務視窗。",
        )
    await runtime.stop()
    request_shutdown()
    return MessageResponse(message="翻譯已停止，程式即將關閉。")
