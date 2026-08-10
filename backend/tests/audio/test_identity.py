from __future__ import annotations

from backend.app.audio.identity import resolve_device_index, resolve_endpoint_index
from backend.app.audio.models import AudioDeviceInfo, LoopbackEndpointInfo


def device(index: int, name: str, host_api: str = "Windows WASAPI") -> AudioDeviceInfo:
    return AudioDeviceInfo(
        index=index,
        name=name,
        host_api=host_api,
        max_input_channels=2,
        default_sample_rate=48000,
        low_input_latency=0.01,
    )


def endpoint(index: int, name: str, *, is_default: bool = False) -> LoopbackEndpointInfo:
    return LoopbackEndpointInfo(
        index=index,
        name=name,
        host_api="Windows WASAPI",
        channels=2,
        default_sample_rate=48000,
        low_input_latency=0.01,
        is_default=is_default,
    )


def test_a_device_is_found_at_whatever_index_it_now_has() -> None:
    # The whole point: another device was plugged in, so the saved index would
    # now open the wrong hardware.
    devices = [device(0, "新的 USB 麥克風"), device(1, "Scarlett 2i2 USB")]

    resolved = resolve_device_index(
        devices, name="Scarlett 2i2 USB", host_api="Windows WASAPI"
    )

    assert resolved.index == 1
    assert resolved.notice is None


def test_a_missing_device_selects_nothing_and_says_so() -> None:
    resolved = resolve_device_index(
        [device(0, "內建麥克風")], name="Scarlett 2i2 USB", host_api="Windows WASAPI"
    )

    assert resolved.index is None
    assert resolved.notice is not None
    assert "Scarlett 2i2 USB" in resolved.notice


def test_two_devices_with_the_same_name_are_refused() -> None:
    # Two identical USB microphones cannot be told apart by name. Guessing
    # would silently capture the wrong one.
    devices = [device(0, "USB Microphone"), device(3, "USB Microphone")]

    resolved = resolve_device_index(
        devices, name="USB Microphone", host_api="Windows WASAPI"
    )

    assert resolved.index is None
    assert resolved.notice is not None


def test_the_same_name_under_two_host_apis_still_resolves() -> None:
    # Windows lists one device under MME, DirectSound and WASAPI. The host API
    # is what separates them.
    devices = [
        device(0, "Scarlett 2i2 USB", host_api="MME"),
        device(5, "Scarlett 2i2 USB", host_api="Windows WASAPI"),
    ]

    resolved = resolve_device_index(
        devices, name="Scarlett 2i2 USB", host_api="Windows WASAPI"
    )

    assert resolved.index == 5


def test_a_changed_host_api_falls_back_to_a_unique_name() -> None:
    # A driver reinstall can move a device between host APIs. The name is
    # still unambiguous, so refusing would be unhelpful.
    devices = [device(2, "Scarlett 2i2 USB", host_api="MME")]

    resolved = resolve_device_index(
        devices, name="Scarlett 2i2 USB", host_api="Windows WASAPI"
    )

    assert resolved.index == 2
    assert resolved.notice is None


def test_nothing_saved_means_nothing_to_restore() -> None:
    resolved = resolve_device_index([device(0, "內建麥克風")], name=None, host_api=None)

    assert resolved.index is None
    assert resolved.notice is None


def test_an_endpoint_is_found_by_name() -> None:
    endpoints = [endpoint(0, "喇叭 (Realtek)"), endpoint(1, "HDMI 輸出")]

    resolved = resolve_endpoint_index(endpoints, name="HDMI 輸出")

    assert resolved.index == 1
    assert resolved.notice is None


def test_a_missing_endpoint_falls_back_to_the_default_output() -> None:
    # `None` means "whatever Windows is playing to right now", which is the
    # safe fallback rather than an arbitrary endpoint.
    resolved = resolve_endpoint_index(
        [endpoint(0, "喇叭 (Realtek)", is_default=True)], name="HDMI 輸出"
    )

    assert resolved.index is None
    assert resolved.notice is not None
    assert "HDMI 輸出" in resolved.notice


def test_no_saved_endpoint_is_not_a_problem() -> None:
    resolved = resolve_endpoint_index([endpoint(0, "喇叭 (Realtek)")], name=None)

    assert resolved.index is None
    assert resolved.notice is None
