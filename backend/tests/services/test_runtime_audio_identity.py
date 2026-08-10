from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from backend.app.audio.devices import AudioDeviceError
from backend.app.audio.models import AudioDeviceInfo, LoopbackEndpointInfo
from backend.app.services.runtime import PipelineRuntime

_SETTINGS: dict[str, Any] = {
    "audio": {
        "source_kind": "input_device",
        "device_index": None,
        "device_name": None,
        "device_host_api": None,
        "loopback_endpoint_index": None,
        "loopback_endpoint_name": None,
        "channel": 1,
        "raw_queue_capacity": 32,
        "pcm_queue_capacity": 50,
    },
    "gemini": {
        "model": "gemini-3.5-live-translate-preview",
        "target_language_code": "zh-Hant",
        "echo_target_language": True,
        "session_rotation_seconds": 480,
    },
    "caption": {"max_payload_length": 4096},
}


def device(index: int, name: str, host_api: str = "Windows WASAPI") -> AudioDeviceInfo:
    return AudioDeviceInfo(
        index=index,
        name=name,
        host_api=host_api,
        max_input_channels=2,
        default_sample_rate=48000,
        low_input_latency=0.01,
    )


def endpoint(index: int, name: str) -> LoopbackEndpointInfo:
    return LoopbackEndpointInfo(
        index=index,
        name=name,
        host_api="Windows WASAPI",
        channels=2,
        default_sample_rate=48000,
        low_input_latency=0.01,
        is_default=index == 0,
    )


def build(
    tmp_path: Path,
    *,
    devices: list[AudioDeviceInfo] | None = None,
    endpoints: list[LoopbackEndpointInfo] | None = None,
    settings: dict[str, Any] | None = None,
) -> tuple[PipelineRuntime, Path]:
    user_settings = tmp_path / "user.yaml"
    runtime = PipelineRuntime(
        settings or _SETTINGS,
        user_settings_path=user_settings,
        device_lister=lambda: list(devices or []),
        loopback_lister=lambda: list(endpoints or []),
    )
    return runtime, user_settings


def stored_audio(path: Path) -> dict[str, Any]:
    return dict(yaml.safe_load(path.read_text(encoding="utf-8"))["audio"])


def test_choosing_a_device_saves_its_name_and_not_its_index(tmp_path: Path) -> None:
    runtime, user_settings = build(
        tmp_path, devices=[device(0, "內建麥克風"), device(3, "Scarlett 2i2 USB")]
    )

    runtime.update_audio_selection(
        source_kind="input_device", device_index=3, endpoint_index=None, channel=2
    )

    audio = stored_audio(user_settings)
    assert audio["device_name"] == "Scarlett 2i2 USB"
    assert audio["device_host_api"] == "Windows WASAPI"
    assert audio["channel"] == 2
    # The index is what breaks across machines, so it must never be written.
    assert "device_index" not in audio


def test_choosing_a_loopback_endpoint_saves_its_name(tmp_path: Path) -> None:
    runtime, user_settings = build(
        tmp_path, endpoints=[endpoint(0, "喇叭 (Realtek)"), endpoint(2, "HDMI 輸出")]
    )

    runtime.update_audio_selection(
        source_kind="wasapi_loopback", device_index=None, endpoint_index=2, channel=None
    )

    audio = stored_audio(user_settings)
    assert audio["source_kind"] == "wasapi_loopback"
    assert audio["loopback_endpoint_name"] == "HDMI 輸出"
    assert audio["device_name"] is None


def test_the_default_output_is_saved_as_no_endpoint_name(tmp_path: Path) -> None:
    # "Whatever Windows is playing to" is already machine independent; there
    # is nothing to look up on the next start.
    runtime, user_settings = build(tmp_path, endpoints=[endpoint(0, "喇叭 (Realtek)")])

    runtime.update_audio_selection(
        source_kind="wasapi_loopback",
        device_index=None,
        endpoint_index=None,
        channel=None,
    )

    assert stored_audio(user_settings)["loopback_endpoint_name"] is None


def test_a_device_that_cannot_be_identified_is_saved_as_unselected(
    tmp_path: Path,
) -> None:
    # Claiming to know the device when enumeration failed would restore a name
    # that was never verified.
    def broken() -> list[AudioDeviceInfo]:
        raise AudioDeviceError("裝置列舉失敗")

    user_settings = tmp_path / "user.yaml"
    runtime = PipelineRuntime(
        _SETTINGS, user_settings_path=user_settings, device_lister=broken
    )

    runtime.update_audio_selection(
        source_kind="input_device", device_index=3, endpoint_index=None, channel=1
    )

    assert stored_audio(user_settings)["device_name"] is None
    # The selection itself still applies to this run.
    assert runtime.settings["audio"]["device_index"] == 3


def test_restart_finds_the_device_at_its_new_index(tmp_path: Path) -> None:
    settings = _deep_copy_with_identity(
        device_name="Scarlett 2i2 USB", device_host_api="Windows WASAPI"
    )
    runtime, _user_settings = build(
        tmp_path,
        devices=[device(0, "新的 USB 攝影機麥克風"), device(4, "Scarlett 2i2 USB")],
        settings=settings,
    )

    runtime.restore_audio_selection()

    assert runtime.settings["audio"]["device_index"] == 4
    assert runtime.audio_notice is None


def test_a_device_that_is_gone_leaves_the_selection_empty_and_explains(
    tmp_path: Path,
) -> None:
    settings = _deep_copy_with_identity(
        device_name="Scarlett 2i2 USB", device_host_api="Windows WASAPI"
    )
    runtime, _user_settings = build(
        tmp_path, devices=[device(0, "內建麥克風")], settings=settings
    )

    runtime.restore_audio_selection()

    assert runtime.settings["audio"]["device_index"] is None
    assert runtime.audio_notice is not None
    assert "Scarlett 2i2 USB" in runtime.audio_notice


def test_choosing_a_source_clears_the_restore_notice(tmp_path: Path) -> None:
    settings = _deep_copy_with_identity(
        device_name="Scarlett 2i2 USB", device_host_api="Windows WASAPI"
    )
    runtime, _user_settings = build(
        tmp_path, devices=[device(0, "內建麥克風")], settings=settings
    )
    runtime.restore_audio_selection()
    assert runtime.audio_notice is not None

    runtime.update_audio_selection(
        source_kind="input_device", device_index=0, endpoint_index=None, channel=1
    )

    assert runtime.audio_notice is None


def test_a_failed_enumeration_at_startup_is_not_fatal(tmp_path: Path) -> None:
    def broken() -> list[AudioDeviceInfo]:
        raise AudioDeviceError("裝置列舉失敗")

    settings = _deep_copy_with_identity(
        device_name="Scarlett 2i2 USB", device_host_api="Windows WASAPI"
    )
    runtime = PipelineRuntime(
        settings, user_settings_path=tmp_path / "user.yaml", device_lister=broken
    )

    runtime.restore_audio_selection()

    assert runtime.settings["audio"]["device_index"] is None
    assert runtime.audio_notice is not None


def test_the_saved_identity_is_reported_in_the_snapshot(tmp_path: Path) -> None:
    settings = _deep_copy_with_identity(
        device_name="Scarlett 2i2 USB", device_host_api="Windows WASAPI"
    )
    runtime, _user_settings = build(
        tmp_path, devices=[device(0, "內建麥克風")], settings=settings
    )
    runtime.restore_audio_selection()

    assert runtime.snapshot().audio_notice == runtime.audio_notice


def _deep_copy_with_identity(**identity: Any) -> dict[str, Any]:
    settings = {key: dict(value) for key, value in _SETTINGS.items()}
    settings["audio"].update(identity)
    return settings


def test_an_unknown_style_field_is_refused(tmp_path: Path) -> None:
    # A typo in a field name must fail loudly rather than be stored and never
    # rendered.
    from backend.app.services.runtime import RuntimeSelectionError

    runtime, _user_settings = build(tmp_path)

    with pytest.raises(RuntimeSelectionError, match="outline"):
        runtime.update_caption_style({"outlinewidth": 4})


def test_a_partial_style_update_leaves_the_other_fields_alone(tmp_path: Path) -> None:
    runtime, _user_settings = build(tmp_path)
    runtime.update_caption_style({"size": 72, "outline_width": 3})

    runtime.update_caption_style({"align": "center"})

    style = runtime.snapshot().style
    assert style["align"] == "center"
    assert style["size"] == 72
    assert style["outline_width"] == 3
