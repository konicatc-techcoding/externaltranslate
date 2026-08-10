from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app.api.app import create_app
from backend.app.captions.presets import PresetStore
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


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    runtime = PipelineRuntime(
        _SETTINGS,
        source_factory=lambda _settings: pytest.fail("source must not be built"),
        provider_factory=lambda **_kwargs: pytest.fail("provider must not be built"),
        preset_store=PresetStore(tmp_path / "caption-presets.json"),
    )
    with TestClient(create_app(runtime=runtime)) as test_client:
        yield test_client


def test_presets_start_empty(client: TestClient) -> None:
    assert client.get("/api/caption-presets").json() == {"presets": []}


def test_saving_captures_the_settings_in_force(client: TestClient) -> None:
    client.put(
        "/api/settings/caption-layout", json={"chars_per_line": 10, "max_lines": 3}
    )
    client.put(
        "/api/settings/caption-style",
        json={
            "font": "kai",
            "size": 72,
            "scroll": False,
            "scroll_ms": 400,
            "color": "#FFCC00",
        },
    )

    response = client.put("/api/caption-presets", json={"name": "記者會"})
    assert response.status_code == 200
    saved = response.json()["presets"][0]
    assert saved == {
        "name": "記者會",
        "chars_per_line": 10,
        "max_lines": 3,
        "font": "kai",
        "size": 72,
        "color": "#FFCC00",
        "scroll": False,
        "scroll_ms": 400,
    }


def test_applying_a_preset_restores_every_setting(client: TestClient) -> None:
    client.put(
        "/api/settings/caption-layout", json={"chars_per_line": 10, "max_lines": 3}
    )
    client.put(
        "/api/settings/caption-style",
        json={
            "font": "kai",
            "size": 72,
            "scroll": False,
            "scroll_ms": 400,
            "color": "#FFCC00",
        },
    )
    client.put("/api/caption-presets", json={"name": "記者會"})

    # move everything away from the saved values
    client.put(
        "/api/settings/caption-layout", json={"chars_per_line": 30, "max_lines": 1}
    )
    client.put(
        "/api/settings/caption-style",
        json={
            "font": "jhenghei",
            "size": 20,
            "scroll": True,
            "scroll_ms": 200,
            "color": "#00FF00",
        },
    )

    assert client.post("/api/caption-presets/記者會/apply").status_code == 200

    settings = client.get("/api/settings").json()
    assert settings["caption_chars_per_line"] == 10
    assert settings["caption_max_lines"] == 3
    assert settings["caption_font"] == "kai"
    assert settings["caption_size"] == 72
    assert settings["caption_color"] == "#FFCC00"
    assert settings["caption_scroll"] is False
    assert settings["caption_scroll_ms"] == 400


def test_deleting_a_preset(client: TestClient) -> None:
    client.put("/api/caption-presets", json={"name": "暫存"})
    response = client.delete("/api/caption-presets/暫存")
    assert response.status_code == 200
    assert response.json() == {"presets": []}


def test_unknown_preset_is_a_404(client: TestClient) -> None:
    assert client.post("/api/caption-presets/沒有這個/apply").status_code == 404
    assert client.delete("/api/caption-presets/沒有這個").status_code == 404


def test_blank_or_oversized_name_is_rejected(client: TestClient) -> None:
    assert client.put("/api/caption-presets", json={"name": ""}).status_code == 422
    assert (
        client.put("/api/caption-presets", json={"name": "x" * 200}).status_code == 422
    )
    assert client.get("/api/caption-presets").json() == {"presets": []}


def test_preset_payload_carries_no_credential(client: TestClient) -> None:
    client.put("/api/credentials", json={"api_key": "AIzaSyFAKEKEY"})
    client.put("/api/caption-presets", json={"name": "主畫面"})

    body = client.get("/api/caption-presets").text
    assert "AIzaSyFAKEKEY" not in body
    assert "api_key" not in body
