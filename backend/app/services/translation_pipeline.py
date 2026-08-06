from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from backend.app.audio.sources.base import AudioSource
from backend.app.translation.base import (
    TranslationEventSink,
    TranslationProvider,
    TranslationProviderError,
    TranslationSession,
)
from backend.app.translation.models import TranslationEventKind


class TranslationPipelineError(RuntimeError):
    """The audio-to-translation pipeline could not continue safely."""


ReconnectWaiter = Callable[[asyncio.Event, float], Awaitable[bool]]


class TranslationPipeline:
    def __init__(
        self,
        *,
        pcm_poll_timeout: float = 0.1,
        session_rotation_seconds: float = 480.0,
        reconnect_delays: tuple[float, ...] = (0.5, 1.0, 2.0, 4.0, 5.0),
        reconnect_waiter: ReconnectWaiter | None = None,
    ) -> None:
        if pcm_poll_timeout <= 0:
            raise ValueError("pcm_poll_timeout 必須大於 0。")
        if session_rotation_seconds <= 0:
            raise ValueError("session_rotation_seconds 必須大於 0。")
        if not reconnect_delays or any(delay < 0 for delay in reconnect_delays):
            raise ValueError("reconnect_delays必須包含至少一個大於等於0的秒數。")
        self._pcm_poll_timeout = pcm_poll_timeout
        self._session_rotation_seconds = session_rotation_seconds
        self._reconnect_delays = reconnect_delays
        self._reconnect_waiter = reconnect_waiter or self._wait_for_stop

    async def run(
        self,
        *,
        source: AudioSource,
        provider: TranslationProvider,
        stop_event: asyncio.Event,
        event_sink: TranslationEventSink,
    ) -> None:
        source_start_attempted = True
        pcm_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1)
        reader_stop = asyncio.Event()
        reader: asyncio.Task[None] | None = None
        primary_error: BaseException | None = None
        stop_failed = False
        reader_failed = False
        try:
            try:
                await asyncio.to_thread(source.start)
            except Exception:
                primary_error = TranslationPipelineError(
                    "音訊來源啟動失敗；請重新列舉裝置並確認driver、連線與選擇設定。"
                )
            if primary_error is None:
                reader = asyncio.create_task(
                    self._read_audio(source, pcm_queue, reader_stop),
                    name="translation-pcm-reader",
                )
                try:
                    await self._supervise_sessions(
                        pcm_queue=pcm_queue,
                        reader=reader,
                        provider=provider,
                        stop_event=stop_event,
                        event_sink=event_sink,
                    )
                except asyncio.CancelledError as exc:
                    primary_error = exc
                except TranslationPipelineError as exc:
                    primary_error = exc
                except Exception:
                    primary_error = TranslationPipelineError(
                        "翻譯pipeline非預期失敗；已停止以保護音訊與credential邊界。"
                    )
        finally:
            reader_stop.set()
            if source_start_attempted:
                try:
                    await asyncio.to_thread(source.stop)
                except Exception:
                    stop_failed = True
            if reader is not None:
                reader_result = (await asyncio.gather(reader, return_exceptions=True))[0]
                reader_failed = isinstance(reader_result, BaseException) and not isinstance(
                    reader_result, asyncio.CancelledError
                )

        if stop_failed or reader_failed:
            if isinstance(primary_error, asyncio.CancelledError):
                message = "取消翻譯pipeline時資源cleanup失敗；音訊來源可能尚未完整釋放。"
            elif primary_error is not None:
                message = "翻譯pipeline工作與資源cleanup同時失敗；已禁止繼續執行。"
            elif stop_failed and reader_failed:
                message = "音訊來源停止與PCM reader cleanup同時失敗；請重新啟動程序。"
            elif stop_failed:
                message = "音訊來源停止失敗，資源可能仍由本程序持有；請重新啟動程序。"
            else:
                message = "PCM reader工作失敗；請確認音訊裝置、driver與連線狀態。"
            primary_error = TranslationPipelineError(message)

        if primary_error is not None:
            raise primary_error

    async def _supervise_sessions(
        self,
        *,
        pcm_queue: asyncio.Queue[bytes],
        reader: asyncio.Task[None],
        provider: TranslationProvider,
        stop_event: asyncio.Event,
        event_sink: TranslationEventSink,
    ) -> None:
        reconnect_attempt = 0
        while not stop_event.is_set():
            if reader.done():
                reader_error: TranslationPipelineError | None = None
                try:
                    await reader
                except Exception:
                    reader_error = TranslationPipelineError(
                        "PCM reader已失敗；已停止Gemini session重連。"
                    )
                if reader_error is not None:
                    raise reader_error
                raise TranslationPipelineError(
                    "PCM reader非預期結束；已停止Gemini session重連。"
                )
            mapped_error: TranslationPipelineError | None = None
            try:
                async with provider.connect() as session:
                    outcome = await self._run_session(
                        pcm_queue=pcm_queue,
                        reader=reader,
                        session=session,
                        stop_event=stop_event,
                        event_sink=event_sink,
                    )
            except TranslationPipelineError:
                raise
            except TranslationProviderError as exc:
                if not exc.retryable:
                    mapped_error = TranslationPipelineError(
                        "Gemini翻譯連線無法恢復；請檢查API權限與設定。"
                    )
                else:
                    delay = self._reconnect_delays[
                        min(reconnect_attempt, len(self._reconnect_delays) - 1)
                    ]
                    reconnect_attempt += 1
                    if await self._reconnect_waiter(stop_event, delay):
                        return
                    continue
            except Exception:
                mapped_error = TranslationPipelineError(
                    "Gemini provider非預期失敗；已停止以避免洩漏SDK錯誤內容。"
                )
            if mapped_error is not None:
                raise mapped_error
            reconnect_attempt = 0
            if outcome == "stop":
                return

    async def _run_session(
        self,
        *,
        pcm_queue: asyncio.Queue[bytes],
        reader: asyncio.Task[None],
        session: TranslationSession,
        stop_event: asyncio.Event,
        event_sink: TranslationEventSink,
    ) -> str:
        sender = asyncio.create_task(
            self._send_audio(pcm_queue, session), name="translation-audio-sender"
        )
        receiver = asyncio.create_task(
            self._receive_events(session, event_sink),
            name="translation-event-receiver",
        )
        stopper = asyncio.create_task(
            stop_event.wait(), name="translation-stop-waiter"
        )
        rotator = asyncio.create_task(
            asyncio.sleep(self._session_rotation_seconds),
            name="translation-session-rotator",
        )
        session_tasks: set[asyncio.Task[Any]] = {sender, receiver, stopper, rotator}
        outcome: str | None = None
        primary_error: BaseException | None = None
        primary_task: asyncio.Task[Any] | None = None
        try:
            done, _pending = await asyncio.wait(
                session_tasks | {reader}, return_when=asyncio.FIRST_COMPLETED
            )
            if reader in done:
                try:
                    await reader
                except Exception:
                    primary_error = TranslationPipelineError(
                        "音訊來源讀取失敗；請確認裝置仍連線且driver運作正常。"
                    )
                else:
                    primary_error = TranslationPipelineError(
                        "音訊來源讀取工作非預期結束。"
                    )
            else:
                completed_workers = [
                    task for task in (sender, receiver) if task in done
                ]
                if completed_workers:
                    primary_task = completed_workers[0]
                elif stopper in done:
                    outcome = "stop"
                else:
                    outcome = "rotate"

            if primary_task is not None:
                try:
                    worker_outcome = await primary_task
                except asyncio.CancelledError as exc:
                    primary_error = exc
                except TranslationProviderError as exc:
                    primary_error = exc
                except Exception:
                    primary_error = TranslationPipelineError(
                        "Gemini翻譯工作失敗；請檢查網路、API權限與服務狀態。"
                    )
                else:
                    if primary_task is receiver and worker_outcome == "rotate":
                        outcome = "rotate"
                    else:
                        primary_error = TranslationPipelineError(
                            "Gemini翻譯工作非預期結束；請檢查網路與API服務狀態。"
                        )
        except BaseException as exc:
            primary_error = exc
        finally:
            for task in session_tasks:
                if not task.done():
                    task.cancel()
            cleanup_tasks = tuple(session_tasks)
            cleanup_results = await asyncio.gather(
                *cleanup_tasks, return_exceptions=True
            )

        cleanup_failed = any(
            isinstance(result, BaseException)
            and not isinstance(result, asyncio.CancelledError)
            and task is not primary_task
            for task, result in zip(cleanup_tasks, cleanup_results, strict=True)
        )
        if cleanup_failed:
            if isinstance(primary_error, asyncio.CancelledError):
                message = "取消Gemini session時task cleanup失敗；資源狀態可能不完整。"
            elif primary_error is not None:
                message = "Gemini session工作與task cleanup同時失敗；已停止自動重連。"
            else:
                message = "Gemini session task cleanup失敗；已停止自動重連。"
            primary_error = TranslationPipelineError(message)

        if primary_error is not None:
            raise primary_error
        if outcome is None:
            raise TranslationPipelineError("Gemini session未產生可辨識的結束狀態。")
        return outcome

    @staticmethod
    async def _wait_for_stop(stop_event: asyncio.Event, delay: float) -> bool:
        if delay == 0:
            await asyncio.sleep(0)
            return stop_event.is_set()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=delay)
        except TimeoutError:
            return False
        return True

    async def _read_audio(
        self,
        source: AudioSource,
        pcm_queue: asyncio.Queue[bytes],
        stop_event: asyncio.Event,
    ) -> None:
        while not stop_event.is_set():
            try:
                chunk = await asyncio.to_thread(
                    source.get_pcm_chunk, self._pcm_poll_timeout
                )
            except TimeoutError:
                continue
            if pcm_queue.full():
                with suppress(asyncio.QueueEmpty):
                    pcm_queue.get_nowait()
            pcm_queue.put_nowait(chunk)

    @staticmethod
    async def _send_audio(
        pcm_queue: asyncio.Queue[bytes], session: TranslationSession
    ) -> None:
        while True:
            chunk = await pcm_queue.get()
            await session.send_audio(chunk)

    @staticmethod
    async def _receive_events(
        session: TranslationSession, event_sink: TranslationEventSink
    ) -> str | None:
        async for event in session.receive_events():
            await event_sink(event)
            if event.kind is TranslationEventKind.SESSION_EXPIRING:
                return "rotate"
        return None
