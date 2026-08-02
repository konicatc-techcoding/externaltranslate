from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.config import ConfigurationError, load_settings


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
