from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from backend.app.audio.capture import create_audio_source_from_settings
from backend.app.audio.devices import AudioDeviceError
from backend.app.audio.models import MeterReading
from backend.app.audio.sources.base import AudioSource
from backend.app.audio.sources.input_device import AudioCaptureError
from backend.app.audio.sources.wasapi_loopback import (
    LoopbackCaptureError,
    LoopbackDeviceError,
)
from backend.app.captions.assembler import CaptionAssembler, CaptionEventSink
from backend.app.captions.models import CaptionState
from backend.app.captions.store import CaptionStore
from backend.app.config import (
    CHARS_PER_LINE_RANGE,
    MAX_LINES_RANGE,
    caption_layout,
    caption_max_payload_length,
)
from backend.app.services.translation_pipeline import TranslationPipeline
from backend.app.status.caption_status import publish_caption_status
from backend.app.status.models import RuntimeStatusSnapshot
from backend.app.status.publisher import StatusPublisher
from backend.app.status.store import StatusStore
from backend.app.translation.base import TranslationProvider, TranslationProviderError
from backend.app.translation.gemini_live import GeminiLiveProvider
from backend.app.translation.models import TranslationEvent

_SOURCE_KINDS = ("input_device", "wasapi_loopback")

CredentialTestOutcome = Literal["ok", "auth_failed", "network_error", "not_configured"]

_AUDIO_SELECTION_ERRORS = (
    AudioDeviceError,
    AudioCaptureError,
    LoopbackDeviceError,
    LoopbackCaptureError,
)


class RuntimeServiceError(RuntimeError):
    """Base class for runtime failures surfaced to the local API."""


class RuntimeCredentialError(RuntimeServiceError):
    """Raised when an operation needs a Gemini API key that is not present."""


class RuntimeConflictError(RuntimeServiceError):
    """Raised when an operation conflicts with the current runtime state."""


class RuntimeSelectionError(RuntimeServiceError):
    """Raised when an audio selection is not usable."""


@dataclass(frozen=True)
class RuntimeSnapshot:
    """Everything the local UI needs for one render, all sanitized."""

    running: bool
    status: RuntimeStatusSnapshot
    caption: CaptionState
    meter: MeterReading | None
    last_error: str | None
    elapsed_seconds: float
    layout: tuple[int, int]


SourceFactory = Callable[[Mapping[str, Any]], AudioSource]
ProviderFactory = Callable[..., TranslationProvider]
PipelineFactory = Callable[..., TranslationPipeline]


class PipelineRuntime:
    """Owns every piece of live state for the local application.

    The API key lives here and only here, in process memory: it is never
    written to settings, logs or any response. Routes stay thin wrappers so
    audio and Gemini lifecycles have exactly one owner.
    """

    def __init__(
        self,
        settings: Mapping[str, Any],
        *,
        source_factory: SourceFactory = create_audio_source_from_settings,
        provider_factory: ProviderFactory = GeminiLiveProvider,
        pipeline_factory: PipelineFactory = TranslationPipeline,
    ) -> None:
        self._settings: dict[str, Any] = deepcopy(dict(settings))
        self._source_factory = source_factory
        self._provider_factory = provider_factory
        self._pipeline_factory = pipeline_factory

        self._api_key: str | None = None
        self._status_store = StatusStore()
        self._status_publisher = StatusPublisher(self._status_store)
        self._caption_store = CaptionStore()
        # One assembler for the runtime's life: a per-run assembler would
        # restart revisions at zero and the store, which outlives the run,
        # rejects that as a regression.
        chars_per_line, max_lines = caption_layout(self._settings)
        # Normalize the effective layout back into settings so the API always
        # reports what is actually in force, never a missing key.
        caption_settings = dict(self._settings.get("caption") or {})
        caption_settings["chars_per_line"] = chars_per_line
        caption_settings["max_lines"] = max_lines
        self._settings["caption"] = caption_settings
        self._caption_assembler = CaptionAssembler(
            max_payload_length=caption_max_payload_length(self._settings),
            chars_per_line=chars_per_line,
            max_lines=max_lines,
        )
        self._caption_sink = CaptionEventSink(
            self._caption_assembler, self._caption_store
        )
        self._source: AudioSource | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None
        self._last_error: str | None = None
        # Run duration lives here so it survives a page reload and is correct
        # for a control page opened after the run began.
        self._run_started_at: float | None = None
        self._run_elapsed = 0.0

    def __repr__(self) -> str:  # pragma: no cover - trivial, but must stay safe
        return f"<PipelineRuntime running={self.running} configured={self.has_api_key}>"

    # ------------------------------------------------------------------ state

    @property
    def settings(self) -> Mapping[str, Any]:
        return deepcopy(self._settings)

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def has_api_key(self) -> bool:
        return self._api_key is not None

    @property
    def last_error(self) -> str | None:
        return self._last_error

    # ------------------------------------------------------------ credentials

    def set_api_key(self, api_key: str) -> None:
        cleaned = api_key.strip()
        if not cleaned:
            raise RuntimeCredentialError("尚未提供有效的Gemini API Key。")
        self._api_key = cleaned

    def clear_api_key(self) -> None:
        self._api_key = None

    async def test_api_key(self) -> CredentialTestOutcome:
        """Open and close one provider session to classify the credential.

        Returns a coarse category only. Provider messages never propagate: an
        auth failure and a network failure must be distinguishable without
        exposing what the SDK said.
        """
        if self._api_key is None:
            return "not_configured"
        gemini = self._settings["gemini"]
        provider = self._provider_factory(
            api_key=self._api_key,
            model=gemini["model"],
            target_language_code=gemini["target_language_code"],
            echo_target_language=gemini["echo_target_language"],
        )
        try:
            async with provider.connect():
                return "ok"
        except TranslationProviderError as exc:
            return "network_error" if exc.retryable else "auth_failed"
        except Exception:
            return "network_error"

    # --------------------------------------------------------------- settings

    def update_audio_selection(
        self,
        *,
        source_kind: str,
        device_index: int | None,
        endpoint_index: int | None,
        channel: int | None,
    ) -> None:
        if self.running:
            raise RuntimeConflictError("翻譯執行中無法變更音訊來源；請先停止後再調整。")
        if source_kind not in _SOURCE_KINDS:
            raise RuntimeSelectionError(f"不支援的audio source：{source_kind}。")
        audio = dict(self._settings["audio"])
        audio["source_kind"] = source_kind
        # INPUT_DEVICE XOR WASAPI_LOOPBACK: selecting one clears the other.
        if source_kind == "input_device":
            audio["device_index"] = device_index
            audio["loopback_endpoint_index"] = None
            if channel is not None:
                audio["channel"] = channel
        else:
            audio["device_index"] = None
            audio["loopback_endpoint_index"] = endpoint_index
        self._settings["audio"] = audio

    def update_caption_layout(self, *, chars_per_line: int, max_lines: int) -> None:
        """Change the display layout, re-flowing immediately.

        Deliberately allowed while running: unlike the audio source, adjusting
        how many characters fit on a line must not require taking captions off
        air. The reflowed state is committed so the next snapshot carries it.
        """
        low, high = CHARS_PER_LINE_RANGE
        if not low <= chars_per_line <= high:
            raise RuntimeSelectionError(
                f"每行字數必須介於 {low} 到 {high} 之間。"
            )
        low_lines, high_lines = MAX_LINES_RANGE
        if not low_lines <= max_lines <= high_lines:
            raise RuntimeSelectionError(
                f"行數必須介於 {low_lines} 到 {high_lines} 之間。"
            )

        caption = dict(self._settings.get("caption") or {})
        caption["chars_per_line"] = chars_per_line
        caption["max_lines"] = max_lines
        self._settings["caption"] = caption

        state = self._caption_assembler.set_layout(
            chars_per_line=chars_per_line, max_lines=max_lines
        )
        self._caption_store.commit(state)

    # -------------------------------------------------------------- lifecycle

    async def start(self) -> None:
        if self.running:
            raise RuntimeConflictError("翻譯已在執行中。")
        if self._api_key is None:
            raise RuntimeCredentialError("尚未設定Gemini API Key，無法開始翻譯。")

        gemini = self._settings["gemini"]
        try:
            source = self._source_factory(self._settings)
        except _AUDIO_SELECTION_ERRORS as exc:
            # These carry our own actionable Traditional Chinese messages
            # (missing device index, endpoint gone). Collapsing them into a
            # generic failure would leave the user with nothing to act on.
            raise RuntimeSelectionError(str(exc)) from None
        provider = self._provider_factory(
            api_key=self._api_key,
            model=gemini["model"],
            target_language_code=gemini["target_language_code"],
            echo_target_language=gemini["echo_target_language"],
        )
        pipeline = self._pipeline_factory(
            session_rotation_seconds=gemini["session_rotation_seconds"],
            status_publisher=self._status_publisher,
        )
        # Start from an empty caption so the previous run's text does not look
        # like output from this one.
        self._caption_store.commit(self._caption_assembler.reset())
        caption_sink = self._caption_sink
        caption_store = self._caption_store
        publisher = self._status_publisher

        async def event_sink(event: TranslationEvent) -> None:
            before = caption_store.snapshot()
            await caption_sink(event)
            state = caption_store.snapshot()
            if state is not before:
                # Otherwise the control page shows caption_sink idle while
                # captions are streaming.
                publish_caption_status(publisher, state)

        self._last_error = None
        self._source = source
        # Each run times itself from zero.
        self._run_elapsed = 0.0
        self._run_started_at = time.monotonic()
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(
            self._run(
                pipeline=pipeline,
                source=source,
                provider=provider,
                stop_event=self._stop_event,
                event_sink=event_sink,
            ),
            name="externaltranslate-pipeline",
        )

    async def _run(
        self,
        *,
        pipeline: TranslationPipeline,
        source: AudioSource,
        provider: TranslationProvider,
        stop_event: asyncio.Event,
        event_sink: Callable[[TranslationEvent], Any],
    ) -> None:
        try:
            await pipeline.run(
                source=source,
                provider=provider,
                stop_event=stop_event,
                event_sink=event_sink,
            )
        except Exception as exc:
            # Record the message only. The pipeline has already published the
            # precise component state (fail_closed for an unrecoverable
            # credential problem); publishing a generic error here would
            # overwrite it and hide why translation stopped.
            self._last_error = str(exc) or "翻譯pipeline失敗；請檢查裝置、網路與API設定。"
        finally:
            # Freeze the duration here rather than in stop(): a run that ends
            # on its own must still report how long it lasted.
            if self._run_started_at is not None:
                self._run_elapsed = time.monotonic() - self._run_started_at
                self._run_started_at = None

    async def stop(self) -> None:
        task = self._task
        if task is None:
            return
        if self._stop_event is not None:
            self._stop_event.set()
        try:
            await task
        except asyncio.CancelledError:  # pragma: no cover - defensive
            pass
        finally:
            self._task = None
            self._stop_event = None
            self._source = None

    # --------------------------------------------------------------- snapshot

    @property
    def elapsed_seconds(self) -> float:
        started_at = self._run_started_at
        if started_at is None:
            return self._run_elapsed
        return time.monotonic() - started_at

    def snapshot(self) -> RuntimeSnapshot:
        source = self._source
        return RuntimeSnapshot(
            elapsed_seconds=self.elapsed_seconds,
            layout=caption_layout(self._settings),
            running=self.running,
            status=self._status_store.snapshot(),
            caption=self._caption_store.snapshot(),
            meter=source.latest_meter if source is not None else None,
            last_error=self._last_error,
        )
