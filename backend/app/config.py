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
