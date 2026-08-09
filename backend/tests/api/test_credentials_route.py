from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app.api.app import create_app
from backend.app.services.runtime import PipelineRuntime
from backend.app.translation.base import TranslationProviderError

_KEY = "AIzaSyFAKEKEYFAKEKEYFAKEKEY"

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


class _OkProvider:
    @asynccontextmanager
    async def connect(self) -> AsyncIterator[object]:
        yield object()


def _client(provider_factory: Any = None) -> Iterator[TestClient]:
    runtime = PipelineRuntime(
        _SETTINGS,
        source_factory=lambda _settings: pytest.fail("source must not be built"),
        provider_factory=provider_factory or (lambda **_kwargs: _OkProvider()),
    )
    with TestClient(create_app(runtime=runtime)) as client:
        yield client


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield from _client()


def test_credential_state_starts_unconfigured(client: TestClient) -> None:
    assert client.get("/api/credentials").json() == {"configured": False}


def test_submitting_a_key_never_echoes_any_part_of_it(client: TestClient) -> None:
    response = client.put("/api/credentials", json={"api_key": _KEY})
    assert response.status_code == 200
    assert response.json() == {"configured": True}
    assert _KEY not in response.text
    # not even a masked tail
    assert _KEY[-4:] not in response.text

    state = client.get("/api/credentials")
    assert state.json() == {"configured": True}
    assert _KEY not in state.text


def test_clearing_the_key(client: TestClient) -> None:
    client.put("/api/credentials", json={"api_key": _KEY})
    assert client.delete("/api/credentials").json() == {"configured": False}
    assert client.get("/api/credentials").json() == {"configured": False}


def test_blank_key_is_rejected(client: TestClient) -> None:
    assert client.put("/api/credentials", json={"api_key": ""}).status_code == 422
    assert client.put("/api/credentials", json={"api_key": "   "}).status_code == 422
    assert client.get("/api/credentials").json() == {"configured": False}


def test_unknown_field_is_rejected(client: TestClient) -> None:
    response = client.put(
        "/api/credentials", json={"api_key": _KEY, "remember": True}
    )
    assert response.status_code == 422


def test_key_never_reaches_the_logs(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        client.put("/api/credentials", json={"api_key": _KEY})
        client.post("/api/credentials/test")
        client.get("/api/pipeline/status")
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert _KEY not in rendered


def test_credential_test_reports_ok(client: TestClient) -> None:
    client.put("/api/credentials", json={"api_key": _KEY})
    body = client.post("/api/credentials/test").json()
    assert body["result"] == "ok"
    assert body["message"]


def test_credential_test_without_key(client: TestClient) -> None:
    assert client.post("/api/credentials/test").json()["result"] == "not_configured"


def test_credential_test_classifies_failures_without_leaking_sdk_text() -> None:
    class _AuthFailingProvider:
        @asynccontextmanager
        async def connect(self) -> AsyncIterator[object]:
            raise TranslationProviderError(
                "raw sdk detail 0xdeadbeef", retryable=False
            )
            yield object()

    class _FlakyProvider:
        @asynccontextmanager
        async def connect(self) -> AsyncIterator[object]:
            raise TranslationProviderError("raw sdk detail 0xdeadbeef", retryable=True)
            yield object()

    for factory, expected in (
        (lambda **_kwargs: _AuthFailingProvider(), "auth_failed"),
        (lambda **_kwargs: _FlakyProvider(), "network_error"),
    ):
        for client in _client(factory):
            client.put("/api/credentials", json={"api_key": _KEY})
            response = client.post("/api/credentials/test")
            assert response.json()["result"] == expected
            assert "0xdeadbeef" not in response.text
