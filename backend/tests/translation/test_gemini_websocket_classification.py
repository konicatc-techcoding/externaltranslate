from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from typing import Any

import pytest
from google.genai import types
from websockets.exceptions import ConnectionClosedError, InvalidStatus
from websockets.frames import Close, CloseCode
from websockets.http11 import Response

from backend.app.translation.base import TranslationProviderError
from backend.app.translation.gemini_live import (
    GeminiLiveProvider,
    GeminiLiveSession,
)


def abnormal_close() -> ConnectionClosedError:
    return ConnectionClosedError(
        Close(CloseCode.ABNORMAL_CLOSURE, ""),
        Close(CloseCode.ABNORMAL_CLOSURE, ""),
        True,
    )


def bad_status(status_code: int) -> InvalidStatus:
    return InvalidStatus(Response(status_code, "reason", None))


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


def test_send_transport_abnormal_close_is_retryable() -> None:
    async def scenario() -> None:
        session = GeminiLiveSession(FailingSdkSession(send_error=abnormal_close()))
        with pytest.raises(TranslationProviderError) as caught:
            await session.send_audio(b"\x00\x00" * 1600)
        assert caught.value.retryable is True
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None

    asyncio.run(scenario())


def test_receive_transport_abnormal_close_is_retryable() -> None:
    async def scenario() -> None:
        session = GeminiLiveSession(FailingSdkSession(receive_error=abnormal_close()))
        with pytest.raises(TranslationProviderError) as caught:
            _events = [event async for event in session.receive_events()]
        assert caught.value.retryable is True
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None

    asyncio.run(scenario())


class HandshakeContext(AbstractAsyncContextManager[object]):
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def __aenter__(self) -> object:
        raise self._error

    async def __aexit__(self, *args: object) -> None:
        del args


class HandshakeLive:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def connect(self, *, model: str, config: types.LiveConnectConfig) -> HandshakeContext:
        del model, config
        return HandshakeContext(self._error)


class HandshakeAsyncClient:
    def __init__(self, error: Exception) -> None:
        self.live = HandshakeLive(error)
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class HandshakeClient:
    def __init__(self, status_code: int) -> None:
        self.aio = HandshakeAsyncClient(bad_status(status_code))
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    ("status_code", "expected_retryable"),
    [(429, True), (503, True), (408, True), (403, False), (401, False)],
)
def test_handshake_invalid_status_classification(
    status_code: int, expected_retryable: bool
) -> None:
    async def scenario() -> None:
        client = HandshakeClient(status_code)
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
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None

    asyncio.run(scenario())
