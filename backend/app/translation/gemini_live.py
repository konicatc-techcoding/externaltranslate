from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Protocol

from google import genai
from google.genai import errors, types

from backend.app.translation.base import TranslationProviderError
from backend.app.translation.models import TranslationEvent, TranslationEventKind


class _SdkSession(Protocol):
    async def send_realtime_input(self, **kwargs: Any) -> None: ...

    def receive(self) -> AsyncIterator[types.LiveServerMessage]: ...


class _LiveApi(Protocol):
    def connect(
        self, *, model: str, config: types.LiveConnectConfig
    ) -> AbstractAsyncContextManager[_SdkSession]: ...


class _AsyncClient(Protocol):
    live: _LiveApi

    async def aclose(self) -> None: ...


class _Client(Protocol):
    aio: _AsyncClient

    def close(self) -> None: ...


ClientFactory = Callable[[str], _Client]


def _create_client(api_key: str) -> _Client:
    return genai.Client(api_key=api_key)  # type: ignore[return-value]


def _is_retryable_sdk_error(exc: Exception) -> bool:
    if isinstance(exc, errors.APIError):
        return (
            exc.code in {408, 409, 425, 429}
            or 500 <= exc.code <= 599
            or exc.code in {1001, 1006, 1011, 1012, 1013, 1014}
        )
    websocket_retryable = _is_retryable_websocket_transport(exc)
    if websocket_retryable is not None:
        return websocket_retryable
    return isinstance(exc, (ConnectionError, OSError, TimeoutError))


def _is_retryable_websocket_transport(exc: Exception) -> bool | None:
    """Classify websockets transport/handshake errors, or None if not ours."""
    try:
        from websockets.exceptions import ConnectionClosed, InvalidStatus
    except ImportError:  # pragma: no cover - google-genai always pins websockets
        return None
    if isinstance(exc, ConnectionClosed):
        # Abnormal/live-drop closures are transient; a clean 1000 offers no
        # transport-level diagnostic and is not retried by classification.
        # Use rcvd/sent Close frames to avoid the deprecated `.code` accessor.
        code: int | None = None
        for frame in (getattr(exc, "rcvd", None), getattr(exc, "sent", None)):
            candidate = getattr(frame, "code", None)
            if isinstance(candidate, int):
                code = candidate
                break
        if code is None:
            return True  # abnormal closure without a close frame
        return code != 1000
    if isinstance(exc, InvalidStatus):
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status is None:
            return False
        return status in {408, 409, 425, 429} or 500 <= status <= 599
    return None


async def _close_client(client: _Client) -> None:
    cleanup_error: BaseException | None = None
    try:
        await client.aio.aclose()
    except BaseException as exc:
        # Capture CancelledError and raw SDK detail; never let it escape raw.
        cleanup_error = exc
    try:
        client.close()
    except BaseException as exc:
        if cleanup_error is None:
            cleanup_error = exc
    if cleanup_error is not None:
        raise TranslationProviderError(
            "Gemini client關閉失敗，連線資源可能尚未完整釋放。"
        )


class GeminiLiveSession:
    def __init__(self, session: _SdkSession) -> None:
        self._session = session

    async def send_audio(self, pcm_chunk: bytes) -> None:
        if len(pcm_chunk) != 3200:
            raise TranslationProviderError(
                "Gemini音訊chunk必須是100 ms、16 kHz mono PCM16（3,200 bytes）。"
            )
        mapped_error: TranslationProviderError | None = None
        try:
            await self._session.send_realtime_input(
                audio=types.Blob(
                    data=pcm_chunk,
                    mime_type="audio/pcm;rate=16000",
                )
            )
        except Exception as exc:
            mapped_error = TranslationProviderError(
                "Gemini音訊傳送失敗；請檢查網路與Live API session狀態。",
                retryable=_is_retryable_sdk_error(exc),
            )
        if mapped_error is not None:
            raise mapped_error

    async def receive_events(self) -> AsyncIterator[TranslationEvent]:
        mapped_error: TranslationProviderError | None = None
        # A session boundary is what lets downstream caption state advance its
        # generation and drop stale partials. The matching SESSION_STOPPED is
        # emitted by the pipeline, which owns session teardown: an async
        # generator cannot yield from its own cleanup path.
        yield TranslationEvent(kind=TranslationEventKind.SESSION_STARTED)
        try:
            while True:
                received_message = False
                async for response in self._session.receive():
                    received_message = True
                    if response.go_away is not None:
                        yield TranslationEvent(
                            kind=TranslationEventKind.SESSION_EXPIRING
                        )
                    content = response.server_content
                    if content is None:
                        continue
                    if content.interim_input_transcription is not None:
                        transcription = content.interim_input_transcription
                        yield TranslationEvent(
                            kind=TranslationEventKind.INPUT_TRANSCRIPTION,
                            text=transcription.text,
                            language_code=transcription.language_code,
                            finished=transcription.finished,
                        )
                    if content.input_transcription is not None:
                        transcription = content.input_transcription
                        yield TranslationEvent(
                            kind=TranslationEventKind.INPUT_TRANSCRIPTION,
                            text=transcription.text,
                            language_code=transcription.language_code,
                            finished=transcription.finished,
                        )
                    if content.output_transcription is not None:
                        transcription = content.output_transcription
                        yield TranslationEvent(
                            kind=TranslationEventKind.OUTPUT_TRANSCRIPTION,
                            text=transcription.text,
                            language_code=transcription.language_code,
                            finished=transcription.finished,
                        )
                if not received_message:
                    raise TranslationProviderError(
                        "Gemini Live API session已結束，未收到新的server message。",
                        retryable=True,
                    )
        except TranslationProviderError:
            raise
        except Exception as exc:
            mapped_error = TranslationProviderError(
                "Gemini transcription接收失敗；請檢查網路與Live API session狀態。",
                retryable=_is_retryable_sdk_error(exc),
            )
        if mapped_error is not None:
            raise mapped_error

class GeminiLiveProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        target_language_code: str,
        echo_target_language: bool,
        client_factory: ClientFactory = _create_client,
    ) -> None:
        if not api_key.strip():
            raise TranslationProviderError("尚未提供Gemini API Key。")
        self._api_key = api_key
        self._model = model
        self._target_language_code = target_language_code
        self._echo_target_language = echo_target_language
        self._client_factory = client_factory

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(model={self._model!r}, "
            f"target_language_code={self._target_language_code!r}, configured=True)"
        )

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[GeminiLiveSession]:
        client: _Client | None = None
        mapped_error: TranslationProviderError | None = None
        propagated_error: BaseException | None = None
        consumer_error: BaseException | None = None
        session_exit_error: BaseException | None = None
        cleanup_error: TranslationProviderError | None = None
        try:
            try:
                client = self._client_factory(self._api_key)
            except TranslationProviderError as exc:
                mapped_error = exc
            except Exception as exc:
                mapped_error = TranslationProviderError(
                    "Gemini Live Translate連線失敗；請確認API Key、網路、帳務與Preview權限。",
                    retryable=_is_retryable_sdk_error(exc),
                )
            except BaseException as exc:
                propagated_error = exc
            if client is not None:
                config = types.LiveConnectConfig(
                    response_modalities=[types.Modality.AUDIO],
                    input_audio_transcription=types.AudioTranscriptionConfig(),
                    output_audio_transcription=types.AudioTranscriptionConfig(),
                    translation_config=types.TranslationConfig(
                        target_language_code=self._target_language_code,
                        echo_target_language=self._echo_target_language,
                    ),
                )
                context: AbstractAsyncContextManager[_SdkSession] = (
                    client.aio.live.connect(model=self._model, config=config)
                )
                try:
                    session = await context.__aenter__()
                except TranslationProviderError as exc:
                    mapped_error = exc
                except Exception as exc:
                    mapped_error = TranslationProviderError(
                        "Gemini Live Translate連線失敗；請確認API Key、網路、帳務與Preview權限。",
                        retryable=_is_retryable_sdk_error(exc),
                    )
                except BaseException as exc:
                    propagated_error = exc
                else:
                    try:
                        yield GeminiLiveSession(session)
                    except BaseException as exc:
                        consumer_error = exc
                    finally:
                        try:
                            await context.__aexit__(None, None, None)
                        except BaseException as exc:
                            session_exit_error = exc
        finally:
            if client is not None:
                try:
                    await _close_client(client)
                except TranslationProviderError as exc:
                    cleanup_error = exc

        work_error: BaseException | None = (
            propagated_error if propagated_error is not None else consumer_error
        )
        if session_exit_error is not None:
            work_cancel = isinstance(work_error, asyncio.CancelledError)
            work_retryable = (
                work_error.retryable
                if isinstance(work_error, TranslationProviderError)
                else False
            )
            if cleanup_error is not None:
                raise TranslationProviderError(
                    "取消Gemini session時session與client cleanup同時失敗；資源狀態可能不完整。"
                    if work_cancel
                    else "Gemini session工作與session/client cleanup同時失敗；已停止自動重連。"
                ) from None
            raise TranslationProviderError(
                "取消Gemini session時session cleanup失敗；資源狀態可能不完整。"
                if work_cancel
                else "Gemini session工作與session cleanup同時失敗；已停止自動重連。",
                retryable=work_retryable,
            ) from None
        if cleanup_error is not None:
            if isinstance(work_error, asyncio.CancelledError):
                raise TranslationProviderError(
                    "取消Gemini session時client cleanup失敗；連線資源可能尚未完整釋放。"
                ) from None
            if work_error is not None or mapped_error is not None:
                raise TranslationProviderError(
                    "Gemini session工作與client cleanup同時失敗；已停止自動重連。"
                ) from None
            raise cleanup_error
        if propagated_error is not None:
            raise propagated_error
        if consumer_error is not None:
            raise consumer_error
        if mapped_error is not None:
            raise mapped_error
