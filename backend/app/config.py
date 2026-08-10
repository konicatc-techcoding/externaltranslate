from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args

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
    "device_name",
    "device_host_api",
    "loopback_endpoint_index",
    "loopback_endpoint_name",
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
_CAPTION_LAYOUT_KEYS = {"max_payload_length", "chars_per_line", "max_lines"}

# Display layout bounds; a caption narrower than 4 full-width characters or
# taller than 10 lines is not a caption any consumer can use.
CHARS_PER_LINE_RANGE = (4, 60)
MAX_LINES_RANGE = (1, 10)
DEFAULT_CHARS_PER_LINE = 20
DEFAULT_MAX_LINES = 2

# Font choices are a closed whitelist: the playout machine must have the font
# installed or the browser silently falls back, which looks like the setting
# was ignored. Noto Sans TC is not bundled with Windows.
CaptionFont = Literal["jhenghei", "kai", "noto-sans-tc"]
CAPTION_FONTS: tuple[str, ...] = get_args(CaptionFont)
DEFAULT_CAPTION_FONT = "jhenghei"
CAPTION_SIZE_RANGE = (12, 200)
DEFAULT_CAPTION_SIZE = 48
SCROLL_MS_RANGE = (120, 1000)
DEFAULT_SCROLL_MS = 250
DEFAULT_SCROLL = True
# Strict #RRGGBB only: the value ends up in a CSS variable, and anything
# looser turns a colour field into a style injection point.
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
DEFAULT_CAPTION_COLOR = "#FFFFFF"

CAPTION_ALIGNMENTS: tuple[str, ...] = ("left", "center", "right")
CAPTION_WEIGHTS: tuple[str, ...] = ("normal", "bold")
OUTLINE_WIDTH_RANGE = (0, 8)
PADDING_RANGE = (0, 64)
RADIUS_RANGE = (0, 48)


@dataclass(frozen=True)
class CaptionStyleField:
    """One appearance setting: its default, its check and its message.

    Appearance grew from three fields to twelve, and repeating the same
    validate-here / default-there / copy-into-the-model dance for each one is
    how a field ends up accepted by the API but silently ignored. Everything
    that needs the list reads it from here.
    """

    name: str
    default: Any
    check: Callable[[Any], bool]
    error: str


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _is_hex_color(value: Any) -> bool:
    return isinstance(value, str) and HEX_COLOR.fullmatch(value) is not None


def _is_ratio(value: Any) -> bool:
    # `0` and `1` arrive as ints from YAML and JSON; both are valid opacities.
    return isinstance(value, int | float) and not isinstance(value, bool) and (
        0.0 <= float(value) <= 1.0
    )


def _bounded(bounds: tuple[int, int]) -> Callable[[Any], bool]:
    def check(value: Any) -> bool:
        return _is_bounded_int(value, minimum=bounds[0], maximum=bounds[1])

    return check


def _one_of(allowed: tuple[str, ...]) -> Callable[[Any], bool]:
    def check(value: Any) -> bool:
        return value in allowed

    return check


CAPTION_STYLE_FIELDS: tuple[CaptionStyleField, ...] = (
    CaptionStyleField(
        "font",
        DEFAULT_CAPTION_FONT,
        _one_of(CAPTION_FONTS),
        f"caption.font 必須是 {'／'.join(CAPTION_FONTS)} 其中之一。",
    ),
    CaptionStyleField(
        "size",
        DEFAULT_CAPTION_SIZE,
        _bounded(CAPTION_SIZE_RANGE),
        f"caption.size 必須是 {CAPTION_SIZE_RANGE[0]} 到 {CAPTION_SIZE_RANGE[1]} 之間的整數。",
    ),
    CaptionStyleField(
        "weight",
        "normal",
        _one_of(CAPTION_WEIGHTS),
        "caption.weight 必須是 normal 或 bold。",
    ),
    CaptionStyleField(
        "color", DEFAULT_CAPTION_COLOR, _is_hex_color, "caption.color 必須是 #RRGGBB 格式。"
    ),
    # Off by default: an outline appearing on its own would change how every
    # existing overlay looks after an upgrade.
    CaptionStyleField(
        "outline_width",
        0,
        _bounded(OUTLINE_WIDTH_RANGE),
        f"caption.outline_width 必須是 {OUTLINE_WIDTH_RANGE[0]} 到 "
        f"{OUTLINE_WIDTH_RANGE[1]} 之間的整數。",
    ),
    CaptionStyleField(
        "outline_color",
        "#000000",
        _is_hex_color,
        "caption.outline_color 必須是 #RRGGBB 格式。",
    ),
    CaptionStyleField(
        "shadow",
        False,
        _is_bool,
        "caption.shadow 必須是 boolean。",
    ),
    CaptionStyleField(
        "background_color",
        "#000000",
        _is_hex_color,
        "caption.background_color 必須是 #RRGGBB 格式。",
    ),
    CaptionStyleField(
        "background_opacity",
        0.5,
        _is_ratio,
        "caption.background_opacity 必須是 0 到 1 之間的數值。",
    ),
    CaptionStyleField(
        "padding",
        12,
        _bounded(PADDING_RANGE),
        f"caption.padding 必須是 {PADDING_RANGE[0]} 到 {PADDING_RANGE[1]} 之間的整數。",
    ),
    CaptionStyleField(
        "radius",
        8,
        _bounded(RADIUS_RANGE),
        f"caption.radius 必須是 {RADIUS_RANGE[0]} 到 {RADIUS_RANGE[1]} 之間的整數。",
    ),
    CaptionStyleField(
        "align",
        "left",
        _one_of(CAPTION_ALIGNMENTS),
        f"caption.align 必須是 {'／'.join(CAPTION_ALIGNMENTS)} 其中之一。",
    ),
    CaptionStyleField(
        "scroll",
        DEFAULT_SCROLL,
        _is_bool,
        "caption.scroll 必須是 boolean。",
    ),
    CaptionStyleField(
        "scroll_ms",
        DEFAULT_SCROLL_MS,
        _bounded(SCROLL_MS_RANGE),
        f"caption.scroll_ms 必須是 {SCROLL_MS_RANGE[0]} 到 {SCROLL_MS_RANGE[1]} 之間的整數。",
    ),
)

CAPTION_STYLE_FIELDS_BY_NAME = {field.name: field for field in CAPTION_STYLE_FIELDS}
_CAPTION_KEYS = _CAPTION_LAYOUT_KEYS | set(CAPTION_STYLE_FIELDS_BY_NAME)

# Windows device names are short; a longer value is a sign the field is being
# used for something it is not.
MAX_DEVICE_NAME_LENGTH = 200


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
    _validate_caption_settings(settings)
    return settings


def save_user_settings(path: Path, updates: Settings) -> None:
    """Merge non-secret settings into the user settings file.

    This is the same file the loader already reads at ``runtime > user >
    default`` priority, so persistence needs no second mechanism — and moving
    a setup to another machine is a matter of copying one file.

    A file that fails to parse is left alone: overwriting it would destroy
    settings the operator may still want to recover.
    """
    _reject_secret_fields(updates)

    existing: Settings = {}
    if path.exists():
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise ConfigurationError(
                f"使用者設定檔無法解析，已保留原檔不覆寫：{path}（{exc}）"
            ) from None
        if loaded is not None:
            if not isinstance(loaded, dict):
                raise ConfigurationError(f"使用者設定檔根節點必須是 mapping：{path}")
            existing = {str(key): value for key, value in loaded.items()}

    merged = _deep_merge(existing, updates)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_text(
            yaml.safe_dump(merged, allow_unicode=True, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(path)
    except OSError as exc:
        raise ConfigurationError(f"無法寫入使用者設定檔：{exc}") from None


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

    # A device is remembered by name, never by index: an index is a position
    # in an enumeration, so it means different hardware after a replug or on
    # another machine. The index is resolved from the name at startup.
    _require_optional_name(audio, "device_name")
    _require_optional_name(audio, "device_host_api")
    _require_optional_name(audio, "loopback_endpoint_name")
    if source_kind == "wasapi_loopback" and audio.get("device_name") is not None:
        raise ConfigurationError(
            "wasapi_loopback 與 audio.device_name 不可同時設定。"
        )
    if source_kind == "input_device" and (
        audio.get("loopback_endpoint_name") is not None
    ):
        raise ConfigurationError(
            "input_device 與 audio.loopback_endpoint_name 不可同時設定。"
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


def _validate_caption_settings(settings: Settings) -> None:
    caption = settings.get("caption")
    if caption is None:
        return
    if not isinstance(caption, Mapping):
        raise ConfigurationError("caption 必須是 mapping。")

    unknown_fields = set(caption) - _CAPTION_KEYS
    if unknown_fields:
        field = min(str(item) for item in unknown_fields)
        raise ConfigurationError(f"不支援或尚未接線的設定欄位：caption.{field}")

    if not _is_bounded_int(
        caption.get("max_payload_length"), minimum=1, maximum=100_000
    ):
        raise ConfigurationError(
            "caption.max_payload_length 必須是 1 到 100000 之間的整數。"
        )

    if "chars_per_line" in caption and not _is_bounded_int(
        caption.get("chars_per_line"),
        minimum=CHARS_PER_LINE_RANGE[0],
        maximum=CHARS_PER_LINE_RANGE[1],
    ):
        raise ConfigurationError(
            f"caption.chars_per_line 必須是 {CHARS_PER_LINE_RANGE[0]} 到 "
            f"{CHARS_PER_LINE_RANGE[1]} 之間的整數。"
        )

    if "max_lines" in caption and not _is_bounded_int(
        caption.get("max_lines"),
        minimum=MAX_LINES_RANGE[0],
        maximum=MAX_LINES_RANGE[1],
    ):
        raise ConfigurationError(
            f"caption.max_lines 必須是 {MAX_LINES_RANGE[0]} 到 "
            f"{MAX_LINES_RANGE[1]} 之間的整數。"
        )

    _validate_caption_style(caption)


def caption_max_payload_length(settings: Mapping[str, Any]) -> int:
    """Return the validated caption payload limit (defaults to 4096)."""
    caption = settings.get("caption") or {}
    return int(caption.get("max_payload_length", 4096))


def _validate_caption_style(caption: Mapping[str, Any]) -> None:
    for field in CAPTION_STYLE_FIELDS:
        if field.name in caption and not field.check(caption[field.name]):
            raise ConfigurationError(field.error)


def caption_style(settings: Mapping[str, Any]) -> dict[str, Any]:
    """Return the validated overlay appearance settings."""
    caption = settings.get("caption") or {}
    style: dict[str, Any] = {}
    for field in CAPTION_STYLE_FIELDS:
        value = caption.get(field.name, field.default)
        # Colours are compared and rendered as strings; one canonical case
        # keeps "did this change?" from depending on how it was typed.
        style[field.name] = value.upper() if _is_hex_color(value) else value
    return style


def caption_layout(settings: Mapping[str, Any]) -> tuple[int, int]:
    """Return the validated (chars_per_line, max_lines) display layout."""
    caption = settings.get("caption") or {}
    return (
        int(caption.get("chars_per_line", DEFAULT_CHARS_PER_LINE)),
        int(caption.get("max_lines", DEFAULT_MAX_LINES)),
    )


def _require_fixed_audio_int(
    audio: Mapping[str, Any], field: str, *, expected: int
) -> None:
    value = audio.get(field)
    if isinstance(value, bool) or value != expected:
        raise ConfigurationError(
            f"audio.{field} 目前版本固定為 {expected}，其他值尚未接線至 runtime。"
        )


def _require_optional_name(audio: Mapping[str, Any], field: str) -> None:
    value = audio.get(field)
    if value is None:
        return
    if (
        isinstance(value, bool)
        or not isinstance(value, str)
        or not value.strip()
        or len(value) > MAX_DEVICE_NAME_LENGTH
    ):
        raise ConfigurationError(
            f"audio.{field} 必須是 null 或 1 到 {MAX_DEVICE_NAME_LENGTH} 字元的非空字串。"
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
