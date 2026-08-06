from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from backend.app.translation.models import TranslationEvent


class TranslationProviderError(RuntimeError):
    """A provider session failed with a safe, user-facing message."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class TranslationSession(Protocol):
    async def send_audio(self, pcm_chunk: bytes) -> None: ...

    def receive_events(self) -> AsyncIterator[TranslationEvent]: ...


class TranslationProvider(Protocol):
    def connect(self) -> AbstractAsyncContextManager[TranslationSession]: ...


TranslationEventSink = Callable[[TranslationEvent], Awaitable[None]]
