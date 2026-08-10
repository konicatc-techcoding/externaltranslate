from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import get_runtime
from backend.app.api.models import MessageResponse
from backend.app.services.runtime import PipelineRuntime

router = APIRouter(prefix="/api/captions", tags=["captions"])


@router.post("/clear", response_model=MessageResponse)
def clear_captions(
    runtime: Annotated[PipelineRuntime, Depends(get_runtime)],
) -> MessageResponse:
    """Clear the caption on screen; deliberately allowed while translating."""
    runtime.clear_captions()
    return MessageResponse(message="字幕已清除。")
