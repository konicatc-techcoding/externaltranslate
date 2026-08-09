from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.config import (
    ConfigurationError,
    caption_max_payload_length,
    load_settings,
)


def test_load_settings_applies_default_user_and_runtime_priority(tmp_path: Path) -> None:
    default_path = tmp_path / "default.yaml"
    user_path = tmp_path / "user.yaml"
    default_path.write_text(
        "server:\n  host: 127.0.0.1\n  port: 8765\ncaption:\n  max_payload_length: 4096\n",
        encoding="utf-8",
    )
    user_path.write_text("server:\n  port: 9000\n", encoding="utf-8")

    settings = load_settings(
        default_path=default_path,
        user_path=user_path,
        runtime_overrides={"server": {"port": 9100}},
    )

    assert settings["server"] == {"host": "127.0.0.1", "port": 9100}
    assert settings["caption"]["max_payload_length"] == 4096


@pytest.mark.parametrize(
    "secret_key",
    [
        "api_key",
        "GEMINI_API_KEY",
        "client_secret",
        "auth_token",
        "accessToken",
        "key",
        "credential",
    ],
)
def test_load_settings_rejects_secret_fields_in_yaml(
    tmp_path: Path, secret_key: str
) -> None:
    default_path = tmp_path / "default.yaml"
    default_path.write_text(
        f"gemini:\n  {secret_key}: should-not-be-here\n", encoding="utf-8"
    )

    with pytest.raises(ConfigurationError, match=secret_key):
        load_settings(default_path=default_path)


def test_load_settings_rejects_non_string_nested_keys(tmp_path: Path) -> None:
    default_path = tmp_path / "default.yaml"
    default_path.write_text("gemini:\n  1: invalid\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="字串"):
        load_settings(default_path=default_path)


def test_load_settings_rejects_non_string_root_keys(tmp_path: Path) -> None:
    default_path = tmp_path / "default.yaml"
    default_path.write_text("1: invalid\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="字串"):
        load_settings(default_path=default_path)


def test_load_settings_rejects_secret_fields_inside_lists(tmp_path: Path) -> None:
    default_path = tmp_path / "default.yaml"
    default_path.write_text(
        "providers:\n  - name: gemini\n    api_key: should-not-be-here\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="api_key"):
        load_settings(default_path=default_path)


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("source_kind", "unsupported"),
        ("device_index", "volt"),
        ("device_index", -1),
        ("loopback_endpoint_index", "speakers"),
        ("loopback_endpoint_index", -1),
        ("channel", 0),
        ("target_sample_rate", 0),
        ("chunk_duration_ms", 0),
        ("raw_queue_capacity", 0),
        ("pcm_queue_capacity", False),
    ],
)
def test_load_settings_rejects_invalid_audio_values(
    tmp_path: Path, field: str, invalid_value: object
) -> None:
    default_path = tmp_path / "default.yaml"
    default_path.write_text(
        "audio:\n"
        "  source_kind: input_device\n"
        "  device_index: null\n"
        "  loopback_endpoint_index: null\n"
        "  channel: 1\n"
        "  target_sample_rate: 16000\n"
        "  chunk_duration_ms: 100\n"
        "  raw_queue_capacity: 32\n"
        "  pcm_queue_capacity: 50\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match=field):
        load_settings(
            default_path=default_path,
            runtime_overrides={"audio": {field: invalid_value}},
        )


@pytest.mark.parametrize(
    ("field", "unsupported_value"),
    [
        ("target_sample_rate", 44100),
        ("chunk_duration_ms", 200),
        ("raw_queue_capacity", 64),
        ("pcm_queue_capacity", 100),
    ],
)
def test_load_settings_rejects_audio_values_not_wired_to_the_runtime(
    tmp_path: Path, field: str, unsupported_value: int
) -> None:
    default_path = tmp_path / "default.yaml"
    default_path.write_text(
        "audio:\n"
        "  source_kind: input_device\n"
        "  device_index: null\n"
        "  loopback_endpoint_index: null\n"
        "  channel: 1\n"
        "  target_sample_rate: 16000\n"
        "  chunk_duration_ms: 100\n"
        "  raw_queue_capacity: 32\n"
        "  pcm_queue_capacity: 50\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match=f"audio.{field}.*固定"):
        load_settings(
            default_path=default_path,
            runtime_overrides={"audio": {field: unsupported_value}},
        )


def test_load_settings_rejects_unknown_audio_fields(tmp_path: Path) -> None:
    default_path = tmp_path / "default.yaml"
    default_path.write_text(
        "audio:\n"
        "  source_kind: input_device\n"
        "  device_index: null\n"
        "  loopback_endpoint_index: null\n"
        "  channel: 1\n"
        "  target_sample_rate: 16000\n"
        "  chunk_duration_ms: 100\n"
        "  raw_queue_capacity: 32\n"
        "  pcm_queue_capacity: 50\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="audio.unwired_future_option"):
        load_settings(
            default_path=default_path,
            runtime_overrides={"audio": {"unwired_future_option": 123}},
        )


def test_load_settings_rejects_unknown_gemini_fields(tmp_path: Path) -> None:
    default_path = tmp_path / "default.yaml"
    default_path.write_text(
        "gemini:\n"
        "  model: gemini-3.5-live-translate-preview\n"
        "  target_language_code: zh-Hant\n"
        "  echo_target_language: true\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="gemini.unwired_future_option"):
        load_settings(
            default_path=default_path,
            runtime_overrides={"gemini": {"unwired_future_option": 123}},
        )


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("model", ""),
        ("model", 35),
        ("target_language_code", ""),
        ("target_language_code", "not a language"),
        ("echo_target_language", "true"),
    ],
)
def test_load_settings_rejects_invalid_gemini_values(
    tmp_path: Path, field: str, invalid_value: object
) -> None:
    default_path = tmp_path / "default.yaml"
    default_path.write_text(
        "gemini:\n"
        "  model: gemini-3.5-live-translate-preview\n"
        "  target_language_code: zh-Hant\n"
        "  echo_target_language: true\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match=field):
        load_settings(
            default_path=default_path,
            runtime_overrides={"gemini": {field: invalid_value}},
        )


def test_load_settings_accepts_safe_gemini_session_rotation_seconds(
    tmp_path: Path,
) -> None:
    default_path = tmp_path / "default.yaml"
    default_path.write_text(
        "gemini:\n"
        "  model: gemini-3.5-live-translate-preview\n"
        "  target_language_code: zh-Hant\n"
        "  echo_target_language: true\n",
        encoding="utf-8",
    )

    settings = load_settings(
        default_path=default_path,
        runtime_overrides={"gemini": {"session_rotation_seconds": 480}},
    )

    assert settings["gemini"]["session_rotation_seconds"] == 480


@pytest.mark.parametrize("invalid_value", [59, 541, True])
def test_load_settings_rejects_unsafe_gemini_session_rotation_seconds(
    tmp_path: Path, invalid_value: object
) -> None:
    default_path = tmp_path / "default.yaml"
    default_path.write_text(
        "gemini:\n"
        "  model: gemini-3.5-live-translate-preview\n"
        "  target_language_code: zh-Hant\n"
        "  echo_target_language: true\n"
        f"  session_rotation_seconds: {str(invalid_value).lower()}\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="60 到 540"):
        load_settings(default_path=default_path)


@pytest.mark.parametrize(
    "audio_override",
    [
        {
            "source_kind": "input_device",
            "loopback_endpoint_index": 16,
        },
        {
            "source_kind": "wasapi_loopback",
            "device_index": 14,
        },
    ],
)
def test_load_settings_enforces_input_xor_loopback_selection(
    tmp_path: Path, audio_override: dict[str, object]
) -> None:
    default_path = tmp_path / "default.yaml"
    default_path.write_text(
        "audio:\n"
        "  source_kind: input_device\n"
        "  device_index: null\n"
        "  loopback_endpoint_index: null\n"
        "  channel: 1\n"
        "  target_sample_rate: 16000\n"
        "  chunk_duration_ms: 100\n"
        "  raw_queue_capacity: 32\n"
        "  pcm_queue_capacity: 50\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="不可同時設定"):
        load_settings(
            default_path=default_path,
            runtime_overrides={"audio": audio_override},
        )


def test_load_settings_accepts_valid_caption_and_helper_returns_value(
    tmp_path: Path,
) -> None:
    default_path = tmp_path / "default.yaml"
    default_path.write_text(
        "caption:\n  max_payload_length: 2048\n", encoding="utf-8"
    )

    settings = load_settings(default_path=default_path)
    assert caption_max_payload_length(settings) == 2048


def test_load_settings_rejects_caption_non_mapping(tmp_path: Path) -> None:
    default_path = tmp_path / "default.yaml"
    default_path.write_text("caption: 4096\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="caption 必須是 mapping"):
        load_settings(default_path=default_path)


@pytest.mark.parametrize(
    "value",
    [0, -1, 1_000_001, True, 3.5],
)
def test_load_settings_rejects_invalid_max_payload_length(
    tmp_path: Path, value: object
) -> None:
    default_path = tmp_path / "default.yaml"
    default_path.write_text(f"caption:\n  max_payload_length: {value}\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="max_payload_length"):
        load_settings(default_path=default_path)


def test_load_settings_rejects_unknown_caption_field(tmp_path: Path) -> None:
    default_path = tmp_path / "default.yaml"
    default_path.write_text(
        "caption:\n  max_payload_length: 4096\n  line_width: 3\n", encoding="utf-8"
    )

    with pytest.raises(ConfigurationError, match="caption.line_width"):
        load_settings(default_path=default_path)
