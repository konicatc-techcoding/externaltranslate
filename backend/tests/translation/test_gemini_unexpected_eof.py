from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from google.genai import types

from backend.app.translation.base import TranslationProviderError
from backend.app.translation.gemini_live import GeminiLiveSession


class EmptySdkSession:
    async def send_realtime_input(self, **kwargs: object) -> None:
        del kwargs

    def receive(self) -> AsyncIterator[types.LiveServerMessage]:
        async def empty() -> AsyncIterator[types.LiveServerMessage]:
            if False:
                yield types.LiveServerMessage()

        return empty()


def test_unexpected_empty_receive_is_retryable_eof() -> None:
    async def scenario() -> None:
        session = GeminiLiveSession(EmptySdkSession())

        with pytest.raises(TranslationProviderError) as caught:
            _events = [event async for event in session.receive_events()]

        assert caught.value.retryable is True
        assert "session" in str(caught.value)
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None

    asyncio.run(scenario())
