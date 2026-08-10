from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.config import (
    ConfigurationError,
    load_settings,
    vmix_settings,
)

_DEFAULT = """
server:
  host: 127.0.0.1
  port: 8765
vmix:
  host: 127.0.0.1
  port: 8088
  input_guid: null
  input_name: null
  fields:
    - Line1.Text
    - Line2.Text
  min_interval_ms: 200
  timeout_ms: 1000
features:
  transcript_persistence: false
  lan_access: false
  vmix_output: false
"""


@pytest.fixture
def default_path(tmp_path: Path) -> Path:
    path = tmp_path / "default.yaml"
    path.write_text(_DEFAULT, encoding="utf-8")
    return path


def test_defaults_load(default_path: Path) -> None:
    settings = load_settings(default_path)

    vmix = vmix_settings(settings)
    assert vmix["host"] == "127.0.0.1"
    assert vmix["port"] == 8088
    assert vmix["fields"] == ["Line1.Text", "Line2.Text"]
    assert vmix["enabled"] is False


def test_the_feature_flag_is_the_single_switch(default_path: Path) -> None:
    # Two switches that can disagree is one switch too many.
    settings = load_settings(
        default_path, runtime_overrides={"features": {"vmix_output": True}}
    )

    assert vmix_settings(settings)["enabled"] is True


@pytest.mark.parametrize(
    "host",
    [
        "http://127.0.0.1",
        "127.0.0.1:8088",
        "127.0.0.1/api",
        "127.0.0.1?x=1",
        "",
        "   ",
    ],
)
def test_a_host_must_be_a_bare_host(default_path: Path, host: str) -> None:
    # Accepting a whole URL would hand the endpoint to the settings file.
    with pytest.raises(ConfigurationError, match="vmix.host"):
        load_settings(default_path, runtime_overrides={"vmix": {"host": host}})


def test_a_remote_host_is_allowed(default_path: Path) -> None:
    # vMix may run on another machine; the UI carries the plaintext warning.
    settings = load_settings(
        default_path, runtime_overrides={"vmix": {"host": "192.168.1.50"}}
    )

    assert vmix_settings(settings)["host"] == "192.168.1.50"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("port", 0),
        ("port", 70000),
        ("port", "8088"),
        ("min_interval_ms", 10),
        ("min_interval_ms", 99999),
        ("timeout_ms", 0),
        ("timeout_ms", 60000),
        ("fields", "Line1.Text"),
        ("fields", []),
        ("fields", ["Line1.Text", ""]),
        ("fields", ["x" * 200]),
        ("input_guid", 5),
        ("nonsense", 1),
    ],
)
def test_invalid_values_fail_closed(
    default_path: Path, field: str, value: object
) -> None:
    with pytest.raises(ConfigurationError, match=field):
        load_settings(default_path, runtime_overrides={"vmix": {field: value}})


def test_a_secret_cannot_hide_in_the_vmix_block(default_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="password"):
        load_settings(default_path, runtime_overrides={"vmix": {"password": "hunter2"}})
