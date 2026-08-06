from __future__ import annotations

import asyncio
from contextlib import AbstractAsyncContextManager
from typing import Any

import pytest
from google.genai import errors, types

from backend.app.translation.base import TranslationProviderError
from backend.app.translation.gemini_live import GeminiLiveProvider


class FakeSdkSession:
    async def send_realtime_input(self, **kwargs: Any) -> None:
        del kwargs

    def receive(self) -> Any:
        raise NotImplementedError


class FailingConnectContext(AbstractAsyncContextManager[FakeSdkSession]):
    def __init__(self, sdk_error: errors.APIError) -> None:
        self._sdk_error = sdk_error

    async def __aenter__(self) -> FakeSdkSession:
        raise self._sdk_error

    async def __aexit__(self, *args: object) -> None:
        del args


class FailingLive:
    def __init__(self, sdk_error: errors.APIError) -> None:
        self._sdk_error = sdk_error

    def connect(
        self, *, model: str, config: types.LiveConnectConfig
    ) -> FailingConnectContext:
        del model, config
        return FailingConnectContext(self._sdk_error)


class FakeAsyncClient:
    def __init__(self, sdk_error: errors.APIError) -> None:
        self.live = FailingLive(sdk_error)
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class FakeClient:
    def __init__(self, sdk_error: errors.APIError) -> None:
        self.aio = FakeAsyncClient(sdk_error)
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    ("sdk_error", "expected_retryable"),
    [
        (errors.ClientError(401, {"message": "secret-auth-detail"}), False),
        (errors.ClientError(429, {"message": "secret-rate-detail"}), True),
        (errors.ServerError(500, {"message": "secret-server-detail"}), True),
        (errors.APIError(1008, {"message": "secret-policy-detail"}), False),
        (errors.APIError(1011, {"message": "secret-websocket-detail"}), True),
    ],
)
def test_provider_classifies_sdk_connect_errors(
    sdk_error: errors.APIError, expected_retryable: bool
) -> None:
    async def scenario() -> None:
        client = FakeClient(sdk_error)
        provider = GeminiLiveProvider(
            api_key="secret-api-key-value",
            model="gemini-3.5-live-translate-preview",
            target_language_code="zh-Hant",
            echo_target_language=True,
            client_factory=lambda _api_key: client,
        )

        with pytest.raises(TranslationProviderError) as caught:
            async with provider.connect():
                pass

        assert caught.value.retryable is expected_retryable
        assert "secret" not in str(caught.value).lower()
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None
        assert client.aio.closed is True
        assert client.closed is True

    asyncio.run(scenario())
