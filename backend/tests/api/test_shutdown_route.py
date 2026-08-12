from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app.api.app import create_app
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


class RecordingRuntime(PipelineRuntime):
    def __init__(self) -> None:
        super().__init__(
            _SETTINGS,
            source_factory=lambda _settings: pytest.fail("source must not be built"),
            provider_factory=lambda **_kwargs: pytest.fail("provider must not be built"),
            device_lister=lambda: [],
            loopback_lister=lambda: [],
        )
        self.stopped = 0

    async def stop(self) -> None:
        self.stopped += 1


@pytest.fixture
def runtime() -> RecordingRuntime:
    return RecordingRuntime()


@pytest.fixture
def client(runtime: RecordingRuntime) -> Iterator[tuple[TestClient, list[str]]]:
    asked: list[str] = []
    app = create_app(runtime=runtime)
    app.state.request_shutdown = lambda: asked.append("shutdown")
    with TestClient(app) as test_client:
        yield test_client, asked


def test_it_stops_translation_before_letting_go(
    client: tuple[TestClient, list[str]], runtime: RecordingRuntime
) -> None:
    # Exiting without stopping would leave the last caption frozen on the vMix
    # title, with the process that could have cleared it already gone.
    test_client, asked = client

    response = test_client.post("/api/shutdown")

    assert response.status_code == 200
    assert runtime.stopped == 1
    assert asked == ["shutdown"]


def test_the_reply_is_sent_before_the_server_goes_away(
    client: tuple[TestClient, list[str]],
) -> None:
    # The page has to be able to say "closed" rather than show a failed
    # request, so the shutdown is requested, not performed inline.
    test_client, _asked = client

    body = test_client.post("/api/shutdown").json()

    assert "關閉" in body["message"]


def test_an_environment_that_cannot_exit_says_so(runtime: RecordingRuntime) -> None:
    # Started some other way — no hook was registered. Better to say the
    # window has to be closed by hand than to pretend it worked.
    app = create_app(runtime=runtime)
    with TestClient(app) as test_client:
        response = test_client.post("/api/shutdown")

    assert response.status_code == 503
    assert "視窗" in response.json()["detail"]
    assert runtime.stopped == 0
