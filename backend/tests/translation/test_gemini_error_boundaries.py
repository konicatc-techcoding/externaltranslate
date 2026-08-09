from __future__ import annotations

import asyncio
import traceback
from collections.abc import AsyncIterator
from typing import Any

import pytest
from google.genai import errors, types

from backend.app.translation.base import TranslationProviderError
from backend.app.translation.gemini_live import GeminiLiveSession


class FailingSdkSession:
    def __init__(
        self,
        *,
        send_error: Exception | None = None,
        receive_error: Exception | None = None,
    ) -> None:
        self._send_error = send_error
        self._receive_error = receive_error

    async def send_realtime_input(self, **kwargs: Any) -> None:
        del kwargs
        if self._send_error is not None:
            raise self._send_error

    async def receive(self) -> AsyncIterator[types.LiveServerMessage]:
        if self._receive_error is not None:
            raise self._receive_error
        if False:
            yield types.LiveServerMessage()


def assert_safe_error(
    error: TranslationProviderError, *, expected_retryable: bool
) -> None:
    assert error.retryable is expected_retryable
    assert error.__cause__ is None
    assert error.__context__ is None
    rendered = "".join(traceback.format_exception(error))
    assert "secret" not in rendered.lower()


def test_send_auth_error_is_permanent_and_raw_detail_is_detached() -> None:
    async def scenario() -> None:
        session = GeminiLiveSession(
            FailingSdkSession(
                send_error=errors.ClientError(
                    401, {"message": "secret-send-auth-detail"}
                )
            )
        )

        with pytest.raises(TranslationProviderError) as caught:
            await session.send_audio(bytes(3200))

        assert_safe_error(caught.value, expected_retryable=False)

    asyncio.run(scenario())


def test_receive_policy_error_is_permanent_and_raw_detail_is_detached() -> None:
    async def scenario() -> None:
        session = GeminiLiveSession(
            FailingSdkSession(
                receive_error=errors.APIError(
                    1008, {"message": "secret-receive-policy-detail"}
                )
            )
        )

        stream = session.receive_events()
        assert (await anext(stream)).kind.value == "session_started"
        with pytest.raises(TranslationProviderError) as caught:
            await anext(stream)

        assert_safe_error(caught.value, expected_retryable=False)

    asyncio.run(scenario())
