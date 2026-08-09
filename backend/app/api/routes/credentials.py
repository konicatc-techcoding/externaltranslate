from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.api.dependencies import get_runtime
from backend.app.api.models import (
    CredentialState,
    CredentialSubmit,
    CredentialTestResult,
)
from backend.app.services.runtime import PipelineRuntime, RuntimeCredentialError

router = APIRouter(prefix="/api/credentials", tags=["credentials"])

_TEST_MESSAGES = {
    "ok": "Gemini API Key 可正常連線。",
    "auth_failed": "Gemini 拒絕此 API Key；請確認金鑰與專案權限。",
    "network_error": "無法連線 Gemini；請確認網路後再試。",
    "not_configured": "尚未設定 Gemini API Key。",
}


@router.get("", response_model=CredentialState)
def read_credential_state(
    runtime: Annotated[PipelineRuntime, Depends(get_runtime)],
) -> CredentialState:
    # Intentionally no masked fragment, no length, no last4.
    return CredentialState(configured=runtime.has_api_key)


@router.put("", response_model=CredentialState)
def submit_credential(
    payload: CredentialSubmit,
    runtime: Annotated[PipelineRuntime, Depends(get_runtime)],
) -> CredentialState:
    try:
        runtime.set_api_key(payload.api_key)
    except RuntimeCredentialError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from None
    return CredentialState(configured=True)


@router.delete("", response_model=CredentialState)
def clear_credential(
    runtime: Annotated[PipelineRuntime, Depends(get_runtime)],
) -> CredentialState:
    runtime.clear_api_key()
    return CredentialState(configured=False)


@router.post("/test", response_model=CredentialTestResult)
async def test_credential(
    runtime: Annotated[PipelineRuntime, Depends(get_runtime)],
) -> CredentialTestResult:
    result = await runtime.test_api_key()
    return CredentialTestResult(result=result, message=_TEST_MESSAGES[result])
