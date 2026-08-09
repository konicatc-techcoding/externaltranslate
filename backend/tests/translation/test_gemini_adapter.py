from __future__ import annotations

import asyncio
import traceback
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from typing import Any

import pytest
from google.genai import types

from backend.app.translation.base import TranslationProviderError
from backend.app.translation.gemini_live import GeminiLiveProvider, GeminiLiveSession


class FakeSdkSession:
    def __init__(
        self, messages: list[types.LiveServerMessage] | None = None
    ) -> None:
        self.sent: list[dict[str, Any]] = []
        self.messages = messages or []

    async def send_realtime_input(self, **kwargs: Any) -> None:
        self.sent.append(kwargs)

    def receive(self) -> AsyncIterator[types.LiveServerMessage]:
        async def responses() -> AsyncIterator[types.LiveServerMessage]:
            for message in self.messages:
                yield message

        return responses()


class FakeConnectContext(AbstractAsyncContextManager[FakeSdkSession]):
    def __init__(self, live: FakeLive) -> None:
        self._live = live

    async def __aenter__(self) -> FakeSdkSession:
        return self._live.session

    async def __aexit__(self, *args: object) -> None:
        self._live.session_closed = True


class FakeLive:
    def __init__(self) -> None:
        self.session = FakeSdkSession()
        self.session_closed = False
        self.model: str | None = None
        self.config: types.LiveConnectConfig | None = None

    def connect(
        self, *, model: str, config: types.LiveConnectConfig
    ) -> FakeConnectContext:
        self.model = model
        self.config = config
        return FakeConnectContext(self)


class FakeAsyncClient:
    def __init__(self) -> None:
        self.live = FakeLive()
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class FakeClient:
    def __init__(self) -> None:
        self.aio = FakeAsyncClient()
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_provider_uses_official_live_translate_config_and_closes_client() -> None:
    async def scenario() -> None:
        created: list[tuple[str, FakeClient]] = []

        def create_client(api_key: str) -> FakeClient:
            client = FakeClient()
            created.append((api_key, client))
            return client

        provider = GeminiLiveProvider(
            api_key="secret-api-key-value",
            model="gemini-3.5-live-translate-preview",
            target_language_code="zh-Hant",
            echo_target_language=True,
            client_factory=create_client,
        )

        assert "secret-api-key-value" not in repr(provider)
        async with provider.connect():
            pass

        api_key, client = created[0]
        config = client.aio.live.config
        assert api_key == "secret-api-key-value"
        assert client.aio.live.model == "gemini-3.5-live-translate-preview"
        assert config is not None
        assert config.response_modalities == [types.Modality.AUDIO]
        assert config.input_audio_transcription is not None
        assert config.output_audio_transcription is not None
        assert config.translation_config is not None
        assert config.translation_config.target_language_code == "zh-Hant"
        assert config.translation_config.echo_target_language is True
        assert client.aio.live.session_closed is True
        assert client.aio.closed is True
        assert client.closed is True

    asyncio.run(scenario())


def test_provider_maps_client_creation_failure_without_leaking_secret() -> None:
    async def scenario() -> None:
        def fail_client(api_key: str) -> FakeClient:
            raise RuntimeError(f"failed for {api_key}")

        provider = GeminiLiveProvider(
            api_key="secret-api-key-value",
            model="gemini-3.5-live-translate-preview",
            target_language_code="zh-Hant",
            echo_target_language=True,
            client_factory=fail_client,
        )

        with pytest.raises(TranslationProviderError) as caught:
            async with provider.connect():
                pass

        assert "secret-api-key-value" not in str(caught.value)
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None

    asyncio.run(scenario())


def test_provider_attempts_both_client_closes_and_maps_cleanup_failure() -> None:
    class FailingAsyncClient(FakeAsyncClient):
        async def aclose(self) -> None:
            self.closed = True
            raise RuntimeError("secret-async-close-detail")

    class CleanupFailingClient(FakeClient):
        def __init__(self) -> None:
            self.aio = FailingAsyncClient()
            self.closed = False

    async def scenario() -> None:
        client = CleanupFailingClient()
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

        assert "secret" not in str(caught.value).lower()
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None
        assert client.aio.closed is True
        assert client.closed is True

    asyncio.run(scenario())


def test_provider_reports_cancellation_and_client_cleanup_failure() -> None:
    class FailingAsyncClient(FakeAsyncClient):
        async def aclose(self) -> None:
            self.closed = True
            raise RuntimeError("secret-cancel-close-detail")

    class CleanupFailingClient(FakeClient):
        def __init__(self) -> None:
            self.aio = FailingAsyncClient()
            self.closed = False

    async def scenario() -> None:
        client = CleanupFailingClient()
        provider = GeminiLiveProvider(
            api_key="secret-api-key-value",
            model="gemini-3.5-live-translate-preview",
            target_language_code="zh-Hant",
            echo_target_language=True,
            client_factory=lambda _api_key: client,
        )
        entered = asyncio.Event()

        async def consume() -> None:
            async with provider.connect():
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(consume())
        await entered.wait()
        task.cancel()

        with pytest.raises(TranslationProviderError) as caught:
            await task

        assert "取消" in str(caught.value)
        assert "cleanup" in str(caught.value)
        assert "secret" not in str(caught.value).lower()
        assert caught.value.__cause__ is None
        assert client.aio.closed is True
        assert client.closed is True

    asyncio.run(scenario())


def test_provider_sanitizes_aclose_cancellation_and_attempts_sync_close() -> None:
    class CancelCloseAsyncClient(FakeAsyncClient):
        async def aclose(self) -> None:
            self.closed = True
            raise asyncio.CancelledError("secret-aclose-cancel")

    class CancelCloseClient(FakeClient):
        def __init__(self) -> None:
            self.aio = CancelCloseAsyncClient()
            self.closed = False

    async def scenario() -> None:
        client = CancelCloseClient()
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

        assert "secret" not in str(caught.value).lower()
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None
        # sync close must still be attempted even when aclose cancelled
        assert client.closed is True
        assert client.aio.closed is True

    asyncio.run(scenario())


def test_provider_combines_session_exit_failure_with_primary_error() -> None:
    class ExitFailContext(FakeConnectContext):
        async def __aexit__(self, *args: object) -> None:
            self._live.session_closed = True
            raise RuntimeError("secret-sdk-exit-detail")

    class ExitFailLive(FakeLive):
        def connect(
            self, *, model: str, config: types.LiveConnectConfig
        ) -> ExitFailContext:
            self.model = model
            self.config = config
            return ExitFailContext(self)

    class ExitFailAsyncClient(FakeAsyncClient):
        def __init__(self) -> None:
            super().__init__()
            self.live = ExitFailLive()

    class ExitFailClient(FakeClient):
        def __init__(self) -> None:
            self.aio = ExitFailAsyncClient()
            self.closed = False

    async def scenario() -> None:
        client = ExitFailClient()
        provider = GeminiLiveProvider(
            api_key="secret-api-key-value",
            model="gemini-3.5-live-translate-preview",
            target_language_code="zh-Hant",
            echo_target_language=True,
            client_factory=lambda _api_key: client,
        )
        primary = TranslationProviderError("safe retryable", retryable=True)

        with pytest.raises(TranslationProviderError) as caught:
            async with provider.connect():
                raise primary

        rendered = str(caught.value)
        assert "連線失敗" not in rendered
        assert "cleanup" in rendered or "同時失敗" in rendered
        assert caught.value.retryable is True
        assert "secret" not in rendered.lower()
        assert caught.value.__cause__ is None
        # from None suppresses chain rendering: even though a sanitized primary
        # may remain in __context__, the raise is detached (suppress_context)
        # so the raw SDK exit detail and any secret never render.
        assert caught.value.__suppress_context__ is True
        rendered_tb = "".join(
            traceback.format_exception(type(caught.value), caught.value, caught.value.__traceback__)
        )
        assert "secret" not in rendered_tb.lower()
        assert client.aio.live.session_closed is True

    asyncio.run(scenario())



def test_provider_preserves_consumer_exception_while_closing_resources() -> None:
    class ConsumerError(RuntimeError):
        pass

    async def scenario() -> None:
        client = FakeClient()
        provider = GeminiLiveProvider(
            api_key="secret-api-key-value",
            model="gemini-3.5-live-translate-preview",
            target_language_code="zh-Hant",
            echo_target_language=True,
            client_factory=lambda _api_key: client,
        )
        expected = ConsumerError("secret-consumer-detail")

        with pytest.raises(ConsumerError) as caught:
            async with provider.connect():
                raise expected

        assert caught.value is expected
        assert client.aio.live.session_closed is True
        assert client.aio.closed is True
        assert client.closed is True

    asyncio.run(scenario())


def test_provider_detaches_sdk_session_exit_failure() -> None:
    class ExitFailingContext(FakeConnectContext):
        async def __aexit__(self, *args: object) -> None:
            self._live.session_closed = True
            raise RuntimeError("secret-sdk-exit-detail")

    class ExitFailingLive(FakeLive):
        def connect(
            self, *, model: str, config: types.LiveConnectConfig
        ) -> ExitFailingContext:
            self.model = model
            self.config = config
            return ExitFailingContext(self)

    class ExitFailingAsyncClient(FakeAsyncClient):
        def __init__(self) -> None:
            super().__init__()
            self.live = ExitFailingLive()

    class ExitFailingClient(FakeClient):
        def __init__(self) -> None:
            self.aio = ExitFailingAsyncClient()
            self.closed = False

    async def scenario() -> None:
        client = ExitFailingClient()
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

        assert "secret" not in str(caught.value).lower()
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None
        assert caught.value.retryable is False
        assert client.aio.live.session_closed is True
        assert client.aio.closed is True
        assert client.closed is True

    asyncio.run(scenario())


def test_session_sends_pcm16_chunk_with_official_mime_type() -> None:
    async def scenario() -> None:
        sdk_session = FakeSdkSession()
        session = GeminiLiveSession(sdk_session)
        chunk = b"\x01\x00" * 1600

        await session.send_audio(chunk)

        assert len(sdk_session.sent) == 1
        blob = sdk_session.sent[0]["audio"]
        assert isinstance(blob, types.Blob)
        assert blob.data == chunk
        assert blob.mime_type == "audio/pcm;rate=16000"

    asyncio.run(scenario())


def test_session_maps_send_failure_without_leaking_sdk_detail() -> None:
    class SendFailingSession(FakeSdkSession):
        async def send_realtime_input(self, **kwargs: Any) -> None:
            del kwargs
            raise RuntimeError("secret-send-detail")

    async def scenario() -> None:
        session = GeminiLiveSession(SendFailingSession())

        with pytest.raises(TranslationProviderError) as caught:
            await session.send_audio(b"\x00\x00" * 1600)

        assert "secret-send-detail" not in str(caught.value)
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None
        assert caught.value.retryable is False

    asyncio.run(scenario())


def test_session_rejects_pcm_chunk_with_wrong_size_before_sdk_send() -> None:
    async def scenario() -> None:
        sdk_session = FakeSdkSession()
        session = GeminiLiveSession(sdk_session)

        with pytest.raises(TranslationProviderError, match="3,200 bytes"):
            await session.send_audio(b"\x00\x00")

        assert sdk_session.sent == []

    asyncio.run(scenario())


def test_session_maps_transcriptions_and_discards_translated_audio() -> None:
    async def scenario() -> None:
        message = types.LiveServerMessage(
            server_content=types.LiveServerContent(
                interim_input_transcription=types.Transcription(
                    text="hel", language_code="en", finished=False
                ),
                input_transcription=types.Transcription(
                    text="hello", language_code="en", finished=False
                ),
                output_transcription=types.Transcription(
                    text="你好", language_code="zh-Hant", finished=True
                ),
                model_turn=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            inline_data=types.Blob(
                                data=b"translated-audio",
                                mime_type="audio/pcm;rate=24000",
                            )
                        )
                    ],
                ),
            )
        )
        session = GeminiLiveSession(FakeSdkSession([message]))

        event_stream = session.receive_events()
        # the leading session_started boundary is consumed first
        assert (await anext(event_stream)).kind.value == "session_started"
        events = [await anext(event_stream) for _ in range(3)]
        await event_stream.aclose()

        assert [event.kind.value for event in events] == [
            "input_transcription",
            "input_transcription",
            "output_transcription",
        ]
        assert [
            (event.text, event.language_code, event.finished) for event in events
        ] == [
            ("hel", "en", False),
            ("hello", "en", False),
            ("你好", "zh-Hant", True),
        ]
        assert all(not hasattr(event, "audio") for event in events)
        assert b"translated-audio" not in repr(events).encode()

    asyncio.run(scenario())


def test_session_maps_receive_failure_without_leaking_sdk_detail() -> None:
    class ReceiveFailingSession(FakeSdkSession):
        def receive(self) -> AsyncIterator[types.LiveServerMessage]:
            async def responses() -> AsyncIterator[types.LiveServerMessage]:
                raise RuntimeError("secret-receive-detail")
                if False:
                    yield types.LiveServerMessage()

            return responses()

    async def scenario() -> None:
        session = GeminiLiveSession(ReceiveFailingSession())

        with pytest.raises(TranslationProviderError) as caught:
            _events = [event async for event in session.receive_events()]

        assert "secret-receive-detail" not in str(caught.value)
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None
        assert caught.value.retryable is False

    asyncio.run(scenario())


def test_session_receives_transcriptions_across_multiple_model_turns() -> None:
    class MultiTurnSession(FakeSdkSession):
        def __init__(self) -> None:
            super().__init__()
            self.turns = [
                types.LiveServerMessage(
                    server_content=types.LiveServerContent(
                        output_transcription=types.Transcription(
                            text="第一句", language_code="zh-Hant", finished=True
                        ),
                        turn_complete=True,
                    )
                ),
                types.LiveServerMessage(
                    server_content=types.LiveServerContent(
                        output_transcription=types.Transcription(
                            text="第二句", language_code="zh-Hant", finished=True
                        ),
                        turn_complete=True,
                    )
                ),
            ]

        def receive(self) -> AsyncIterator[types.LiveServerMessage]:
            async def responses() -> AsyncIterator[types.LiveServerMessage]:
                if self.turns:
                    yield self.turns.pop(0)

            return responses()

    async def scenario() -> None:
        events = GeminiLiveSession(MultiTurnSession()).receive_events()

        assert (await anext(events)).kind.value == "session_started"
        first = await anext(events)
        second = await anext(events)
        await events.aclose()

        assert [first.text, second.text] == ["第一句", "第二句"]

    asyncio.run(scenario())
