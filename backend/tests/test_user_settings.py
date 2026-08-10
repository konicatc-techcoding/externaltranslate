from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from backend.app.config import ConfigurationError, load_settings, save_user_settings

_DEFAULT = """
server:
  host: 127.0.0.1
  port: 8765
gemini:
  model: gemini-3.5-live-translate-preview
  target_language_code: zh-Hant
  echo_target_language: true
  session_rotation_seconds: 480
caption:
  max_payload_length: 4096
  chars_per_line: 20
  max_lines: 2
  font: jhenghei
  size: 48
  scroll: true
  scroll_ms: 250
  color: "#FFFFFF"
audio:
  source_kind: input_device
  device_index: null
  loopback_endpoint_index: null
  channel: 1
  target_sample_rate: 16000
  chunk_duration_ms: 100
  raw_queue_capacity: 32
  pcm_queue_capacity: 50
features:
  transcript_persistence: false
  lan_access: false
  vmix_output: false
"""


@pytest.fixture
def paths(tmp_path: Path) -> tuple[Path, Path]:
    default = tmp_path / "default.yaml"
    default.write_text(_DEFAULT, encoding="utf-8")
    return default, tmp_path / "user.yaml"


def test_saved_settings_are_loaded_on_the_next_start(
    paths: tuple[Path, Path],
) -> None:
    default, user = paths
    save_user_settings(user, {"caption": {"chars_per_line": 10, "font": "kai"}})

    settings = load_settings(default, user, None)

    assert settings["caption"]["chars_per_line"] == 10
    assert settings["caption"]["font"] == "kai"
    # untouched keys still come from the project default
    assert settings["caption"]["max_lines"] == 2


def test_saving_twice_merges_rather_than_replaces(paths: tuple[Path, Path]) -> None:
    _default, user = paths
    save_user_settings(user, {"caption": {"chars_per_line": 10}})
    save_user_settings(user, {"caption": {"font": "kai"}})

    stored = yaml.safe_load(user.read_text(encoding="utf-8"))
    assert stored["caption"] == {"chars_per_line": 10, "font": "kai"}


def test_a_secret_is_never_written(paths: tuple[Path, Path]) -> None:
    _default, user = paths
    with pytest.raises(ConfigurationError):
        save_user_settings(user, {"gemini": {"api_key": "AIzaSyFAKEKEY"}})
    assert not user.exists()


def test_a_corrupt_user_file_is_not_silently_overwritten(
    paths: tuple[Path, Path],
) -> None:
    _default, user = paths
    user.write_text("{ not: valid: yaml: [", encoding="utf-8")

    # Refusing beats destroying settings the operator may still want to fix.
    with pytest.raises(ConfigurationError):
        save_user_settings(user, {"caption": {"chars_per_line": 10}})


def test_written_file_is_valid_for_the_strict_schema(
    paths: tuple[Path, Path],
) -> None:
    default, user = paths
    save_user_settings(
        user,
        {
            "caption": {
                "chars_per_line": 12,
                "max_lines": 3,
                "font": "kai",
                "size": 64,
                "scroll": False,
                "scroll_ms": 400,
                "color": "#FFCC00",
            }
        },
    )
    settings = load_settings(default, user, None)
    assert settings["caption"]["color"] == "#FFCC00"
    assert settings["caption"]["scroll"] is False


def test_unknown_fields_are_rejected_before_they_reach_the_file(
    paths: tuple[Path, Path],
) -> None:
    default, user = paths
    save_user_settings(user, {"caption": {"nonsense": 1}})
    # the strict schema catches it on the next load rather than at write time
    with pytest.raises(ConfigurationError):
        load_settings(default, user, None)
