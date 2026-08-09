from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app.api.app import create_app
from backend.app.api.dependencies import get_runtime
from backend.app.audio.models import AudioDeviceInfo, LoopbackEndpointInfo
from backend.app.prerequisites.models import PrerequisiteResult, PrerequisiteStatus
from backend.app.services.runtime import PipelineRuntime

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
