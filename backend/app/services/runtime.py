from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypeVar

from backend.app.audio.capture import create_audio_source_from_settings
from backend.app.audio.devices import AudioDeviceError
from backend.app.audio.identity import resolve_device_index, resolve_endpoint_index
from backend.app.audio.models import (
    AudioDeviceInfo,
    LoopbackEndpointInfo,
    MeterReading,
)
from backend.app.audio.sources.base import AudioSource
from backend.app.audio.sources.input_device import AudioCaptureError
from backend.app.audio.sources.wasapi_loopback import (
    LoopbackCaptureError,
    LoopbackDeviceError,
)
from backend.app.captions.assembler import CaptionAssembler, CaptionEventSink
from backend.app.captions.models import CaptionState
from backend.app.captions.presets import CaptionPreset, PresetStore
from backend.app.captions.store import CaptionStore
from backend.app.config import (
    CAPTION_STYLE_FIELDS,
    CHARS_PER_LINE_RANGE,
    MAX_LINES_RANGE,
    ConfigurationError,
    caption_layout,
    caption_max_payload_length,
    caption_sentence_breaks,
    caption_style,
    save_user_settings,
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
    sentence_breaks: bool
    style: dict[str, Any]
    audio_notice: str | None


SourceFactory = Callable[[Mapping[str, Any]], AudioSource]
ProviderFactory = Callable[..., TranslationProvider]
PipelineFactory = Callable[..., TranslationPipeline]
DeviceLister = Callable[[], list[AudioDeviceInfo]]
LoopbackLister = Callable[[], list[LoopbackEndpointInfo]]


def _enumerate_devices() -> list[AudioDeviceInfo]:
    from backend.app.audio.devices import SoundDeviceBackend, enumerate_input_devices

    return enumerate_input_devices(SoundDeviceBackend())


def _enumerate_endpoints() -> list[LoopbackEndpointInfo]:
    from backend.app.audio.sources.wasapi_loopback import enumerate_loopback_endpoints

    return enumerate_loopback_endpoints()


_Listed = TypeVar("_Listed")


def _enumerate_safely(
    lister: Callable[[], list[_Listed]], failure_notice: str
) -> tuple[list[_Listed], str | None]:
    """Enumerate devices without letting a driver problem stop startup."""
    try:
        return (lister(), None)
    except Exception:
        return ([], failure_notice)


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


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
        preset_store: PresetStore | None = None,
        user_settings_path: Path | None = None,
        device_lister: DeviceLister = _enumerate_devices,
        loopback_lister: LoopbackLister = _enumerate_endpoints,
    ) -> None:
        self._settings: dict[str, Any] = deepcopy(dict(settings))
        self._source_factory = source_factory
        self._provider_factory = provider_factory
        self._pipeline_factory = pipeline_factory
        self._user_settings_path = user_settings_path
        self._device_lister = device_lister
        self._loopback_lister = loopback_lister
        self._audio_notice: str | None = None
        self._preset_store = preset_store or PresetStore(
            Path(__file__).resolve().parents[3] / "config" / "caption-presets.json"
        )

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
        caption_settings.update(caption_style(self._settings))
        self._settings["caption"] = caption_settings
        self._caption_assembler = CaptionAssembler(
            max_payload_length=caption_max_payload_length(self._settings),
            chars_per_line=chars_per_line,
            max_lines=max_lines,
            sentence_breaks=caption_sentence_breaks(self._settings),
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
            audio["loopback_endpoint_name"] = None
            if channel is not None:
                audio["channel"] = channel
            identity = self._identify_device(device_index)
            audio["device_name"] = identity[0]
            audio["device_host_api"] = identity[1]
        else:
            audio["device_index"] = None
            audio["device_name"] = None
            audio["device_host_api"] = None
            audio["loopback_endpoint_index"] = endpoint_index
            audio["loopback_endpoint_name"] = self._identify_endpoint(endpoint_index)
        self._settings["audio"] = audio
        # The operator has just answered the question the notice asked.
        self._audio_notice = None
        self._persist_audio_selection()

    def _identify_device(self, index: int | None) -> tuple[str | None, str | None]:
        """Look up the stable identity of a device index, if it has one."""
        if index is None:
            return (None, None)
        try:
            devices = self._device_lister()
        except Exception:
            # Recording a name we could not verify would restore an
            # unverified device on the next start.
            return (None, None)
        for item in devices:
            if item.index == index:
                return (item.name, item.host_api)
        return (None, None)

    def _identify_endpoint(self, index: int | None) -> str | None:
        if index is None:
            # `None` already means "the current Windows default output", which
            # needs no lookup and is correct on any machine.
            return None
        try:
            endpoints = self._loopback_lister()
        except Exception:
            return None
        for item in endpoints:
            if item.index == index:
                return item.name
        return None

    def restore_audio_selection(self) -> None:
        """Recover the last audio source by name, at startup.

        Indexes are never restored from the settings file: an index is a
        position in an enumeration, so the same number can mean different
        hardware after a replug, a reboot, or on another machine. If the saved
        device cannot be identified beyond doubt, the selection stays empty
        and ``audio_notice`` says why — being asked to choose again is much
        cheaper than silently capturing the wrong source.
        """
        audio = dict(self._settings.get("audio") or {})
        source_kind = audio.get("source_kind")
        if not _optional_str(audio.get("device_name")) and not _optional_str(
            audio.get("loopback_endpoint_name")
        ):
            return  # nothing was saved, so there is nothing to look up
        if source_kind == "input_device":
            name = _optional_str(audio.get("device_name"))
            devices, failure = _enumerate_safely(
                self._device_lister,
                "無法列舉音訊裝置，未能還原上次的音訊來源；請重新選擇。",
            )
            resolved = resolve_device_index(
                devices, name=name, host_api=_optional_str(audio.get("device_host_api"))
            )
            audio["device_index"] = resolved.index
            self._audio_notice = (failure if name else None) or resolved.notice
        elif source_kind == "wasapi_loopback":
            name = _optional_str(audio.get("loopback_endpoint_name"))
            endpoints, failure = _enumerate_safely(
                self._loopback_lister,
                "無法列舉系統音源，已改用 Windows 目前的預設輸出。",
            )
            resolved = resolve_endpoint_index(endpoints, name=name)
            audio["loopback_endpoint_index"] = resolved.index
            self._audio_notice = (failure if name else None) or resolved.notice
        self._settings["audio"] = audio

    @property
    def audio_notice(self) -> str | None:
        """Why the saved audio source could not be restored, if it could not."""
        return self._audio_notice

    def update_caption_layout(
        self, *, chars_per_line: int, max_lines: int, sentence_breaks: bool
    ) -> None:
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
        caption["sentence_breaks"] = sentence_breaks
        self._settings["caption"] = caption

        state = self._caption_assembler.set_layout(
            chars_per_line=chars_per_line,
            max_lines=max_lines,
            sentence_breaks=sentence_breaks,
        )
        self._caption_store.commit(state)
        self._persist_caption_settings()

    def update_caption_style(self, style: Mapping[str, Any]) -> None:
        """Change overlay appearance, also allowed while running.

        Appearance does not affect wrapping (the formatter counts columns),
        so nothing is re-flowed and the caption revision stays put. Validation
        walks the config spec rather than a hand-written list of checks: a new
        appearance field is then impossible to add without validating it.
        """
        unknown = set(style) - {field.name for field in CAPTION_STYLE_FIELDS}
        if unknown:
            raise RuntimeSelectionError(f"不支援的字幕樣式欄位：{min(unknown)}。")

        caption = dict(self._settings.get("caption") or {})
        for field in CAPTION_STYLE_FIELDS:
            if field.name not in style:
                continue
            value = style[field.name]
            if not field.check(value):
                raise RuntimeSelectionError(field.error.replace("caption.", ""))
            caption[field.name] = (
                value.upper() if field.name.endswith("color") else value
            )
        self._settings["caption"] = caption
        self._persist_caption_settings()

    @property
    def presets(self) -> PresetStore:
        return self._preset_store

    def current_preset(self, name: str) -> CaptionPreset:
        """Capture the settings in force under ``name``."""
        chars_per_line, max_lines = caption_layout(self._settings)
        return CaptionPreset(
            name=name.strip(),
            chars_per_line=chars_per_line,
            max_lines=max_lines,
            sentence_breaks=caption_sentence_breaks(self._settings),
            **caption_style(self._settings),
        )

    def apply_preset(self, preset: CaptionPreset) -> None:
        """Apply a saved preset; allowed while translating, like its parts."""
        self.update_caption_style(
            {
                field.name: getattr(preset, field.name)
                for field in CAPTION_STYLE_FIELDS
            }
        )
        self.update_caption_layout(
            chars_per_line=preset.chars_per_line,
            max_lines=preset.max_lines,
            sentence_breaks=preset.sentence_breaks,
        )

    def _persist_caption_settings(self) -> None:
        """Remember the caption display settings for the next start.

        Written to the user settings file the loader already reads, so moving
        a setup to another machine is a matter of copying that one file.
        Persistence is a convenience: a failure here must not stop the
        operator from adjusting captions mid-show.
        """
        path = self._user_settings_path
        if path is None:
            return
        caption = dict(self._settings.get("caption") or {})
        chars_per_line, max_lines = caption_layout(self._settings)
        payload = {
            "caption": {
                "chars_per_line": chars_per_line,
                "max_lines": max_lines,
                "sentence_breaks": caption_sentence_breaks(self._settings),
                **caption_style(self._settings),
                "max_payload_length": caption.get("max_payload_length", 4096),
            }
        }
        with suppress(ConfigurationError, OSError):
            self._persist(path, payload)

    def _persist_audio_selection(self) -> None:
        """Remember the audio source by identity, never by index.

        Writing an index would look like it worked and then open different
        hardware after a replug or on another machine. A name that cannot be
        resolved on the next start simply leaves the source unselected.
        """
        path = self._user_settings_path
        if path is None:
            return
        audio = dict(self._settings.get("audio") or {})
        payload = {
            "audio": {
                "source_kind": audio.get("source_kind"),
                "channel": audio.get("channel"),
                "device_name": audio.get("device_name"),
                "device_host_api": audio.get("device_host_api"),
                "loopback_endpoint_name": audio.get("loopback_endpoint_name"),
            }
        }
        with suppress(ConfigurationError, OSError):
            self._persist(path, payload)

    @staticmethod
    def _persist(path: Path, payload: dict[str, Any]) -> None:
        save_user_settings(path, payload)

    def clear_captions(self) -> None:
        """Wipe the caption for the operator, mid-broadcast.

        After a silent stretch the last caption keeps sitting on screen and
        reads as if it were current; clearing it must not require stopping
        translation. The revision advances so every overlay is pushed the
        empty state.
        """
        state = self._caption_assembler.reset()
        self._caption_store.commit(state)
        publish_caption_status(self._status_publisher, state)

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
            sentence_breaks=caption_sentence_breaks(self._settings),
            style=caption_style(self._settings),
            running=self.running,
            status=self._status_store.snapshot(),
            caption=self._caption_store.snapshot(),
            meter=source.latest_meter if source is not None else None,
            last_error=self._last_error,
            audio_notice=self._audio_notice,
        )
