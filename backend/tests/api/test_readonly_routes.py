from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app.api.app import create_app
from backend.app.api.dependencies import get_runtime
from backend.app.audio.models import AudioDeviceInfo, LoopbackEndpointInfo
from backend.app.config import caption_style
from backend.app.prerequisites.models import PrerequisiteResult, PrerequisiteStatus
from backend.app.services.runtime import PipelineRuntime

# The shipped defaults, read from the one spec table rather than restated here:
# a copy would keep passing after a default changed underneath it.
DEFAULT_STYLE = caption_style({})

_SETTINGS: dict[str, Any] = {
    "audio": {
        "source_kind": "wasapi_loopback",
        "device_index": None,
        "loopback_endpoint_index": None,
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

_DEVICE = AudioDeviceInfo(
    index=3,
    name="Line In (Audio Interface)",
    host_api="Windows WASAPI",
    max_input_channels=2,
    default_sample_rate=48000,
    low_input_latency=0.01,
)

_ENDPOINT = LoopbackEndpointInfo(
    index=7,
    name="Speakers (Realtek)",
    host_api="Windows WASAPI",
    channels=2,
    default_sample_rate=48000,
    low_input_latency=0.01,
    is_default=True,
)


@pytest.fixture
def client() -> Iterator[TestClient]:
    runtime = PipelineRuntime(
        _SETTINGS,
        source_factory=lambda _settings: pytest.fail("source must not be built"),
        provider_factory=lambda **_kwargs: pytest.fail("provider must not be built"),
        # Keep device identity lookups off this machine's real hardware.
        device_lister=lambda: [_DEVICE],
        loopback_lister=lambda: [_ENDPOINT],
    )
    app = create_app(
        runtime=runtime,
        prerequisite_reporter=lambda: [
            PrerequisiteResult(
                identifier="python",
                label="Python 3.11",
                status=PrerequisiteStatus.READY,
                required_for="v0.1",
                version="3.11.9",
            ),
            PrerequisiteResult(
                identifier="sounddevice",
                label="sounddevice",
                status=PrerequisiteStatus.NOT_CHECKED,
                required_for="input_device",
            ),
        ],
        device_lister=lambda: [_DEVICE],
        loopback_lister=lambda: [_ENDPOINT],
    )
    app.dependency_overrides[get_runtime] = lambda: runtime
    with TestClient(app) as test_client:
        yield test_client


def test_prerequisites_report_is_reported_verbatim(client: TestClient) -> None:
    response = client.get("/api/prerequisites")
    assert response.status_code == 200
    body = response.json()
    assert [item["identifier"] for item in body["results"]] == ["python", "sounddevice"]
    # not_checked must never be dressed up as ready
    assert body["results"][1]["status"] == "not_checked"


def test_device_and_endpoint_listing(client: TestClient) -> None:
    devices = client.get("/api/devices").json()["devices"]
    assert devices == [
        {
            "index": 3,
            "name": "Line In (Audio Interface)",
            "host_api": "Windows WASAPI",
            "max_input_channels": 2,
            "default_sample_rate": 48000,
        }
    ]
    endpoints = client.get("/api/loopback-endpoints").json()["endpoints"]
    assert endpoints[0]["index"] == 7
    assert endpoints[0]["is_default"] is True


def test_settings_expose_only_non_secret_fields(client: TestClient) -> None:
    body = client.get("/api/settings").json()
    assert body == {
        "source_kind": "wasapi_loopback",
        "device_index": None,
        "loopback_endpoint_index": None,
        "channel": 1,
        "caption_max_payload_length": 4096,
        "caption_chars_per_line": 20,
        "caption_max_lines": 2,
        "caption_sentence_breaks": True,
        "caption_idle_reset_ms": 0,
        "caption_style": DEFAULT_STYLE,
        "vmix": {
            "enabled": False,
            "host": "127.0.0.1",
            "port": 8088,
            "input_guid": None,
            "input_name": None,
            "fields": ["Line1.Text", "Line2.Text"],
            "min_interval_ms": 200,
            "timeout_ms": 1000,
            "manual_input_guid": None,
            "manual_input_name": None,
            "manual_fields": ["Manual1.Text"],
            "manual_slots": ["", "", "", "", ""],
        },
        "ui": {"collapsed": []},
        "session_rotation_seconds": 480,
    }
    assert "api_key" not in str(body).lower()


def test_settings_update_enforces_source_exclusivity(client: TestClient) -> None:
    response = client.put(
        "/api/settings",
        json={"source_kind": "input_device", "device_index": 3, "channel": 1},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source_kind"] == "input_device"
    assert body["device_index"] == 3
    assert body["loopback_endpoint_index"] is None


def test_caption_layout_can_be_changed_through_the_api(client: TestClient) -> None:
    response = client.put(
        "/api/settings/caption-layout", json={"chars_per_line": 10, "max_lines": 5}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["caption_chars_per_line"] == 10
    assert body["caption_max_lines"] == 5
    assert client.get("/api/settings").json()["caption_max_lines"] == 5


def test_caption_layout_rejects_out_of_range_and_unknown_fields(
    client: TestClient,
) -> None:
    for payload in (
        {"chars_per_line": 0, "max_lines": 2},
        {"chars_per_line": 999, "max_lines": 2},
        {"chars_per_line": 10, "max_lines": 0},
        {"chars_per_line": 10, "max_lines": 99},
        {"chars_per_line": 10, "max_lines": 2, "font": "serif"},
    ):
        assert (
            client.put("/api/settings/caption-layout", json=payload).status_code == 422
        )

    # the rejected updates must leave the effective layout untouched
    assert client.get("/api/settings").json()["caption_chars_per_line"] == 20


def test_caption_style_can_be_changed_through_the_api(client: TestClient) -> None:
    response = client.put(
        "/api/settings/caption-style",
        json={
            **DEFAULT_STYLE,
            "font": "kai",
            "size": 64,
            "color": "#FFCC00",
            "weight": "bold",
            "outline_width": 4,
            "outline_color": "#101010",
            "shadow": True,
            "background_opacity": 0,
            "padding": 24,
            "radius": 0,
            "align": "center",
        },
    )
    assert response.status_code == 200
    style = response.json()["caption_style"]
    assert style["font"] == "kai"
    assert style["size"] == 64
    assert style["color"] == "#FFCC00"
    # The outline is what makes captions readable over bright video.
    assert style["outline_width"] == 4
    assert style["outline_color"] == "#101010"
    assert style["shadow"] is True
    assert style["background_opacity"] == 0
    assert style["align"] == "center"


def test_caption_style_rejects_unknown_font_and_out_of_range(
    client: TestClient,
) -> None:
    base = dict(DEFAULT_STYLE)
    for payload in (
        {**base, "font": "comic-sans"},
        {**base, "size": 4},
        {**base, "size": 9999},
        {**base, "scroll_ms": 10},
        {**base, "scroll_ms": 99999},
        {**base, "color": "red"},
        {**base, "color": "#FFF"},
        {**base, "color": "#FFFFFF; background:url(x)"},
        {**base, "weight": "heavy"},
        {**base, "outline_width": 99},
        {**base, "outline_color": "black"},
        {**base, "background_opacity": 2},
        {**base, "padding": -1},
        {**base, "radius": 999},
        {**base, "align": "justify"},
        {**base, "bold": True},
    ):
        assert (
            client.put("/api/settings/caption-style", json=payload).status_code == 422
        ), payload

    assert client.get("/api/settings").json()["caption_style"] == DEFAULT_STYLE


def test_status_carries_the_caption_style(client: TestClient) -> None:
    assert client.get("/api/pipeline/status").json()["style"] == DEFAULT_STYLE


def test_settings_update_rejects_unknown_fields(client: TestClient) -> None:
    response = client.put(
        "/api/settings",
        json={"source_kind": "input_device", "device_index": 3, "api_key": "secret"},
    )
    assert response.status_code == 422


def test_settings_update_rejects_input_device_without_index(client: TestClient) -> None:
    response = client.put("/api/settings", json={"source_kind": "input_device"})
    assert response.status_code == 422
    # the previous selection must survive a rejected update
    assert client.get("/api/settings").json()["source_kind"] == "wasapi_loopback"


def test_settings_update_rejects_unknown_source_kind(client: TestClient) -> None:
    response = client.put("/api/settings", json={"source_kind": "asio"})
    assert response.status_code == 422


def test_device_enumeration_failure_is_a_safe_message(client: TestClient) -> None:
    app = create_app(
        runtime=PipelineRuntime(_SETTINGS),
        device_lister=_raise_device_error,
    )
    with TestClient(app) as failing:
        response = failing.get("/api/devices")
    assert response.status_code == 503
    assert "0xdeadbeef" not in response.text
    assert response.json()["detail"]


def _raise_device_error() -> list[AudioDeviceInfo]:
    from backend.app.audio.devices import AudioDeviceError

    raise AudioDeviceError("裝置列舉失敗；請重新插拔並確認driver。")


def test_sentence_breaks_can_be_turned_off_through_the_api(
    client: TestClient,
) -> None:
    response = client.put(
        "/api/settings/caption-layout",
        json={"chars_per_line": 20, "max_lines": 2, "sentence_breaks": False},
    )

    assert response.status_code == 200
    assert response.json()["caption_sentence_breaks"] is False
    # It reflows the caption, so it belongs with the layout rather than with
    # appearance — the status snapshot has to carry it too.
    assert client.get("/api/pipeline/status").json()["layout"] == {
        "chars_per_line": 20,
        "max_lines": 2,
        "sentence_breaks": False,
        "idle_reset_ms": 0,
    }


def test_the_idle_reset_can_be_set_through_the_api(client: TestClient) -> None:
    response = client.put(
        "/api/settings/caption-layout",
        json={"chars_per_line": 20, "max_lines": 5, "idle_reset_ms": 2500},
    )

    assert response.status_code == 200
    assert response.json()["caption_idle_reset_ms"] == 2500
    # It decides what the caption contains, so an overlay has to see it too.
    assert client.get("/api/pipeline/status").json()["layout"]["idle_reset_ms"] == 2500


@pytest.mark.parametrize("value", [1, 499, 30_001, -1])
def test_an_idle_reset_between_off_and_the_floor_is_refused(
    client: TestClient, value: int
) -> None:
    response = client.put(
        "/api/settings/caption-layout",
        json={"chars_per_line": 20, "max_lines": 2, "idle_reset_ms": value},
    )

    assert response.status_code == 422
    assert client.get("/api/settings").json()["caption_idle_reset_ms"] == 0


def test_omitting_the_idle_reset_leaves_it_off(client: TestClient) -> None:
    # The panel predates this field; a client that does not send it must not
    # have the caption start clearing itself.
    response = client.put(
        "/api/settings/caption-layout", json={"chars_per_line": 20, "max_lines": 2}
    )

    assert response.status_code == 200
    assert response.json()["caption_idle_reset_ms"] == 0
