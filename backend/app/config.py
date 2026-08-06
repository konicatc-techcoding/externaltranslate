from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

Settings = dict[str, Any]
_SECRET_KEYS = {
    "api_key",
    "apikey",
    "credential",
    "credentials",
    "key",
    "password",
    "secret",
    "token",
}
_AUDIO_KEYS = {
    "source_kind",
    "device_index",
    "loopback_endpoint_index",
    "channel",
    "target_sample_rate",
    "chunk_duration_ms",
    "raw_queue_capacity",
    "pcm_queue_capacity",
}
_GEMINI_KEYS = {
    "model",
    "target_language_code",
    "echo_target_language",
    "session_rotation_seconds",
}


class ConfigurationError(ValueError):
    """Raised when a settings source is invalid or contains a secret."""


def load_settings(
    default_path: Path,
    user_path: Path | None = None,
    runtime_overrides: Settings | None = None,
) -> Settings:
    """Load non-secret settings with runtime > user > default priority."""

    settings = _read_yaml(default_path, required=True)
    if user_path is not None and user_path.exists():
        settings = _deep_merge(settings, _read_yaml(user_path, required=False))
    if runtime_overrides:
        _reject_secret_fields(runtime_overrides)
        settings = _deep_merge(settings, runtime_overrides)
    _validate_audio_settings(settings)
    _validate_gemini_settings(settings)
    return settings


def _read_yaml(path: Path, *, required: bool) -> Settings:
    if not path.exists():
        if required:
            raise ConfigurationError(f"找不到必要設定檔：{path}")
        return {}

    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ConfigurationError(f"無法讀取設定檔 {path}：{exc}") from exc

    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ConfigurationError(f"設定檔根節點必須是 mapping：{path}")

    _reject_secret_fields(loaded)
    settings = {str(key): value for key, value in loaded.items()}
    return settings


def _deep_merge(base: Settings, override: Settings) -> Settings:
    merged = deepcopy(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _reject_secret_fields(value: Any, prefix: str = "") -> None:
    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            if not isinstance(key, str):
                location = prefix or "<root>"
                raise ConfigurationError(f"設定欄位名稱必須是字串：{location}.{key}")
            path = f"{prefix}.{key}" if prefix else key
            normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key)
            normalized = normalized.lower().replace("-", "_")
            if normalized in _SECRET_KEYS or any(
                normalized.endswith(f"_{secret_key}")
                for secret_key in _SECRET_KEYS
            ):
                raise ConfigurationError(f"設定檔不得包含秘密欄位：{path}")
            _reject_secret_fields(nested_value, path)
        return

    if isinstance(value, list):
        for index, item in enumerate(value):
            _reject_secret_fields(item, f"{prefix}[{index}]")


def _validate_audio_settings(settings: Settings) -> None:
    audio = settings.get("audio")
    if audio is None:
        return
    if not isinstance(audio, Mapping):
        raise ConfigurationError("audio 必須是 mapping。")

    unknown_fields = set(audio) - _AUDIO_KEYS
    if unknown_fields:
        field = min(str(item) for item in unknown_fields)
        raise ConfigurationError(f"不支援或尚未接線的設定欄位：audio.{field}")

    source_kind = audio.get("source_kind")
    if source_kind not in {"input_device", "wasapi_loopback"}:
        raise ConfigurationError(
            "audio.source_kind 必須是 input_device 或 wasapi_loopback。"
        )

    device_index = audio.get("device_index")
    if device_index is not None and not _is_bounded_int(device_index, minimum=0):
        raise ConfigurationError("audio.device_index 必須是 null 或大於等於 0 的整數。")

    loopback_endpoint_index = audio.get("loopback_endpoint_index")
    if loopback_endpoint_index is not None and not _is_bounded_int(
        loopback_endpoint_index, minimum=0
    ):
        raise ConfigurationError(
            "audio.loopback_endpoint_index 必須是 null 或大於等於 0 的整數。"
        )
    if source_kind == "input_device" and loopback_endpoint_index is not None:
        raise ConfigurationError(
            "input_device 與 loopback_endpoint_index 不可同時設定。"
        )
    if source_kind == "wasapi_loopback" and device_index is not None:
        raise ConfigurationError(
            "wasapi_loopback 與 device_index 不可同時設定。"
        )

    _require_bounded_audio_int(audio, "channel", minimum=1, maximum=64)
    _require_fixed_audio_int(audio, "target_sample_rate", expected=16000)
    _require_fixed_audio_int(audio, "chunk_duration_ms", expected=100)
    _require_fixed_audio_int(audio, "raw_queue_capacity", expected=32)
    _require_fixed_audio_int(audio, "pcm_queue_capacity", expected=50)


def _validate_gemini_settings(settings: Settings) -> None:
    gemini = settings.get("gemini")
    if gemini is None:
        return
    if not isinstance(gemini, Mapping):
        raise ConfigurationError("gemini 必須是 mapping。")

    unknown_fields = set(gemini) - _GEMINI_KEYS
    if unknown_fields:
        field = min(str(item) for item in unknown_fields)
        raise ConfigurationError(f"不支援或尚未接線的設定欄位：gemini.{field}")

    model = gemini.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ConfigurationError("gemini.model 必須是非空字串。")

    target_language_code = gemini.get("target_language_code")
    if not isinstance(target_language_code, str) or re.fullmatch(
        r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", target_language_code
    ) is None:
        raise ConfigurationError("gemini.target_language_code 必須是有效的BCP-47格式。")

    if not isinstance(gemini.get("echo_target_language"), bool):
        raise ConfigurationError("gemini.echo_target_language 必須是boolean。")

    session_rotation_seconds = gemini.get("session_rotation_seconds")
    if session_rotation_seconds is not None and not _is_bounded_int(
        session_rotation_seconds, minimum=60, maximum=540
    ):
        raise ConfigurationError(
            "gemini.session_rotation_seconds 必須是 60 到 540 之間的整數。"
        )


def _require_fixed_audio_int(
    audio: Mapping[str, Any], field: str, *, expected: int
) -> None:
    value = audio.get(field)
    if isinstance(value, bool) or value != expected:
        raise ConfigurationError(
            f"audio.{field} 目前版本固定為 {expected}，其他值尚未接線至 runtime。"
        )


def _require_bounded_audio_int(
    audio: Mapping[str, Any],
    field: str,
    *,
    minimum: int,
    maximum: int,
) -> None:
    value = audio.get(field)
    if not _is_bounded_int(value, minimum=minimum, maximum=maximum):
        raise ConfigurationError(
            f"audio.{field} 必須是 {minimum} 到 {maximum} 之間的整數。"
        )


def _is_bounded_int(
    value: Any,
    *,
    minimum: int,
    maximum: int | None = None,
) -> bool:
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return value >= minimum and (maximum is None or value <= maximum)
