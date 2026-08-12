from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
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


def _runtime() -> PipelineRuntime:
    return PipelineRuntime(
        _SETTINGS,
        source_factory=lambda _settings: pytest.fail("source must not be built"),
        provider_factory=lambda **_kwargs: pytest.fail("provider must not be built"),
        device_lister=lambda: [],
        loopback_lister=lambda: [],
    )


@pytest.fixture
def built(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<div id=root>控制台</div>", encoding="utf-8")
    (dist / "assets" / "index.js").write_text("console.log(1)", encoding="utf-8")
    return dist


@pytest.fixture
def client(built: Path) -> Iterator[TestClient]:
    app = create_app(runtime=_runtime(), frontend_dist=built)
    with TestClient(app) as test_client:
        yield test_client


def test_the_control_page_is_served_by_the_backend(client: TestClient) -> None:
    # One process, one port: no second terminal running a dev server, and the
    # page is same-origin with the API it calls.
    response = client.get("/")

    assert response.status_code == 200
    assert "控制台" in response.text


def test_the_overlay_path_serves_the_same_document(client: TestClient) -> None:
    # The app picks its page from `window.location.pathname`, so /overlay is
    # the same file — the server must not look for a file of that name.
    response = client.get("/overlay")

    assert response.status_code == 200
    assert "控制台" in response.text


def test_the_overlay_keeps_its_query_string(client: TestClient) -> None:
    assert client.get("/overlay?lines=3").status_code == 200


def test_assets_are_served(client: TestClient) -> None:
    response = client.get("/assets/index.js")

    assert response.status_code == 200
    assert "console.log" in response.text


def test_the_api_still_wins(client: TestClient) -> None:
    # Serving the page must not shadow the routes the page calls.
    assert client.get("/api/settings").status_code == 200


def test_an_unknown_path_is_not_the_page(client: TestClient) -> None:
    # No catch-all: a mistyped API path should say 404, not return HTML that
    # the caller then fails to parse as JSON.
    assert client.get("/api/nonsense").status_code == 404
    assert client.get("/nonsense").status_code == 404


def test_a_missing_build_leaves_the_api_working(tmp_path: Path) -> None:
    # A checkout that has not been built yet still serves the API, so the
    # failure is "the page is missing", not "nothing works".
    app = create_app(runtime=_runtime(), frontend_dist=tmp_path / "absent")
    with TestClient(app) as client:
        assert client.get("/api/settings").status_code == 200
        assert client.get("/").status_code == 404
        assert app.state.frontend_dist is None


def test_the_served_directory_is_reported(client: TestClient, built: Path) -> None:
    # The launcher prints this so an operator can tell a stale build from a
    # missing one.
    assert client.app.state.frontend_dist == built  # type: ignore[attr-defined]


def test_the_document_is_never_cached(client: TestClient) -> None:
    # Asset names carry a content hash, so a cached index.html keeps asking
    # for the previous build's files — which the upgrade deleted.
    for path in ("/", "/overlay"):
        assert client.get(path).headers["cache-control"] == "no-store"
