from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from backend.app.audio.capture import create_audio_source_from_settings
from backend.app.audio.devices import AudioDeviceError
from backend.app.audio.sources.base import AudioSource
from backend.app.audio.sources.input_device import AudioCaptureError
from backend.app.audio.sources.wasapi_loopback import (
    LoopbackCaptureError,
    LoopbackDeviceError,
)
from backend.app.config import ConfigurationError, load_settings
from backend.app.services.translation_pipeline import (
    TranslationPipeline,
    TranslationPipelineError,
)
from backend.app.translation.base import TranslationProvider, TranslationProviderError
from backend.app.translation.gemini_live import GeminiLiveProvider
from backend.app.translation.models import TranslationEvent, TranslationEventKind


class GeminiSmokeError(RuntimeError):
    """A safe, actionable Stage 2 CLI error."""


def resolve_api_key(
    environ: Mapping[str, str],
    *,
    prompt: Callable[[str], str] = getpass.getpass,
) -> str:
    api_key = environ.get("GEMINI_API_KEY")
    if api_key is None:
        api_key = prompt("請輸入Gemini API Key（只保留於本次程序記憶體）：")
    api_key = api_key.strip()
    if not api_key:
        raise GeminiSmokeError("尚未提供有效的Gemini API Key。")
    return api_key


def build_runtime_overrides(
    *,
    source_kind: str,
    device_index: int | None,
    endpoint_index: int | None,
    channel: int | None,
) -> dict[str, Any]:
    audio: dict[str, Any] = {"source_kind": source_kind}
    if source_kind == "input_device":
        audio["loopback_endpoint_index"] = None
        if device_index is not None:
            audio["device_index"] = device_index
        if channel is not None:
            audio["channel"] = channel
    elif source_kind == "wasapi_loopback":
        audio["device_index"] = None
        if endpoint_index is not None:
            audio["loopback_endpoint_index"] = endpoint_index
    else:
        raise GeminiSmokeError(f"不支援的audio source：{source_kind}。")
    return {"audio": audio}


class _ProviderFactory(Protocol):
    def __call__(
        self,
        *,
        api_key: str,
        model: str,
        target_language_code: str,
        echo_target_language: bool,
    ) -> TranslationProvider: ...


def create_runtime(
    settings: Mapping[str, Any],
    *,
    api_key: str,
    source_factory: Callable[[Mapping[str, Any]], AudioSource] = (
        create_audio_source_from_settings
    ),
    provider_factory: _ProviderFactory = GeminiLiveProvider,
) -> tuple[AudioSource, TranslationProvider]:
    gemini = settings.get("gemini")
    if not isinstance(gemini, Mapping):
        raise GeminiSmokeError("缺少已驗證的Gemini設定。")
    model = gemini.get("model")
    target_language_code = gemini.get("target_language_code")
    echo_target_language = gemini.get("echo_target_language")
    if (
        not isinstance(model, str)
        or not isinstance(target_language_code, str)
        or not isinstance(echo_target_language, bool)
    ):
        raise GeminiSmokeError("Gemini設定尚未完成驗證，無法建立翻譯session。")

    source = source_factory(settings)
    provider = provider_factory(
        api_key=api_key,
        model=model,
        target_language_code=target_language_code,
        echo_target_language=echo_target_language,
    )
    return source, provider


def render_event(
    event: TranslationEvent, *, show_text: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "event": event.kind.value,
        "language_code": event.language_code,
        "finished": event.finished,
        "text_length": len(event.text or ""),
    }
    if show_text:
        payload["text"] = event.text
    return payload


class _Pipeline(Protocol):
    async def run(
        self,
        *,
        source: AudioSource,
        provider: TranslationProvider,
        stop_event: asyncio.Event,
        event_sink: Callable[[TranslationEvent], Any],
    ) -> None: ...


def create_pipeline(
    settings: Mapping[str, Any],
    *,
    pipeline_factory: Callable[..., _Pipeline] = TranslationPipeline,
) -> _Pipeline:
    gemini = settings.get("gemini")
    if not isinstance(gemini, Mapping):
        raise GeminiSmokeError("缺少已驗證的Gemini設定。")
    session_rotation_seconds = gemini.get("session_rotation_seconds")
    if isinstance(session_rotation_seconds, bool) or not isinstance(
        session_rotation_seconds, int
    ):
        raise GeminiSmokeError("Gemini session rotation設定尚未完成驗證。")
    return pipeline_factory(session_rotation_seconds=session_rotation_seconds)


async def run_translation_smoke(
    *,
    source: AudioSource,
    provider: TranslationProvider,
    duration_seconds: float,
    show_text: bool,
    emit: Callable[[dict[str, Any]], None],
    pipeline: _Pipeline | None = None,
) -> dict[str, int]:
    if duration_seconds <= 0:
        raise GeminiSmokeError("duration必須大於0秒。")

    counts = {
        "input_transcription_events": 0,
        "output_transcription_events": 0,
        "finished_output_events": 0,
    }
    valid_output_received = False
    stop_event = asyncio.Event()

    async def collect(event: TranslationEvent) -> None:
        nonlocal valid_output_received
        if event.kind is TranslationEventKind.INPUT_TRANSCRIPTION:
            counts["input_transcription_events"] += 1
        elif event.kind is TranslationEventKind.OUTPUT_TRANSCRIPTION:
            counts["output_transcription_events"] += 1
            if event.finished is True:
                counts["finished_output_events"] += 1
            if (
                event.language_code == "zh-Hant"
                and bool((event.text or "").strip())
            ):
                valid_output_received = True
        emit(render_event(event, show_text=show_text))

    async def stop_after_duration() -> None:
        await asyncio.sleep(duration_seconds)
        stop_event.set()

    timer = asyncio.create_task(
        stop_after_duration(), name="gemini-smoke-duration"
    )
    try:
        active_pipeline = pipeline or TranslationPipeline()
        await active_pipeline.run(
            source=source,
            provider=provider,
            stop_event=stop_event,
            event_sink=collect,
        )
    finally:
        timer.cancel()
        await asyncio.gather(timer, return_exceptions=True)

    if not valid_output_received:
        raise GeminiSmokeError(
            "測試期間未收到有效的繁體中文output transcription；"
            "請確認播放內容含語音、"
            "音量足夠且來源選擇正確。"
        )
    return counts


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ExternalTranslate Stage 2 Gemini Live Translate smoke test"
    )
    parser.add_argument("--user-config", type=Path)
    parser.add_argument(
        "--source-kind",
        choices=("input_device", "wasapi_loopback"),
        required=True,
    )
    parser.add_argument("--device-index", type=int)
    parser.add_argument("--endpoint-index", type=int)
    parser.add_argument("--channel", type=int)
    parser.add_argument("--duration", type=float, default=20.0)
    parser.add_argument("--show-text", action="store_true")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] = os.environ,
    prompt: Callable[[str], str] = getpass.getpass,
    emit: Callable[[str], None] = print,
) -> int:
    args = _parser().parse_args(argv)
    project_root = Path(__file__).resolve().parents[3]
    try:
        runtime_overrides = build_runtime_overrides(
            source_kind=args.source_kind,
            device_index=args.device_index,
            endpoint_index=args.endpoint_index,
            channel=args.channel,
        )
        settings = load_settings(
            project_root / "config" / "default.yaml",
            args.user_config,
            runtime_overrides,
        )
        api_key = resolve_api_key(environ, prompt=prompt)
        source, provider = create_runtime(settings, api_key=api_key)
        pipeline = create_pipeline(settings)

        def emit_event(payload: dict[str, Any]) -> None:
            emit(json.dumps(payload, ensure_ascii=False))

        report = asyncio.run(
            run_translation_smoke(
                source=source,
                provider=provider,
                duration_seconds=args.duration,
                show_text=args.show_text,
                emit=emit_event,
                pipeline=pipeline,
            )
        )
        emit(
            json.dumps(
                {"status": "ok", "summary": report}, ensure_ascii=False
            )
        )
        return 0
    except (
        AudioCaptureError,
        AudioDeviceError,
        ConfigurationError,
        GeminiSmokeError,
        LoopbackCaptureError,
        LoopbackDeviceError,
        TranslationPipelineError,
        TranslationProviderError,
        ValueError,
    ) as exc:
        emit(
            json.dumps(
                {"status": "error", "message": str(exc)}, ensure_ascii=False
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
