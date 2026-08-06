from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from google.genai import types

from backend.app.translation.gemini_live import GeminiLiveSession
from backend.app.translation.models import TranslationEventKind


class GoAwaySdkSession:
    def __init__(self) -> None:
        self._sent = False

    async def send_realtime_input(self, **kwargs: Any) -> None:
        del kwargs

    def receive(self) -> AsyncIterator[types.LiveServerMessage]:
        async def responses() -> AsyncIterator[types.LiveServerMessage]:
            if not self._sent:
                self._sent = True
                yield types.LiveServerMessage(go_away={"time_left": "5s"})
                return
            await asyncio.Event().wait()
            if False:
                yield types.LiveServerMessage()

        return responses()


def test_session_maps_go_away_to_provider_neutral_expiring_event() -> None:
    async def scenario() -> None:
        session = GeminiLiveSession(GoAwaySdkSession())
        event_stream = session.receive_events()

        event = await asyncio.wait_for(anext(event_stream), timeout=0.05)
        await event_stream.aclose()

        assert event.kind is TranslationEventKind.SESSION_EXPIRING
        assert event.text is None
        assert not hasattr(event, "time_left")

    asyncio.run(scenario())
