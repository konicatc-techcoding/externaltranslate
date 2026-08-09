from __future__ import annotations

import pytest

from backend.app.api.app import create_app, resolve_bind_host
from backend.app.config import ConfigurationError


def test_loopback_host_is_accepted() -> None:
    assert resolve_bind_host("127.0.0.1") == "127.0.0.1"
    assert resolve_bind_host("localhost") == "127.0.0.1"
    assert resolve_bind_host(None) == "127.0.0.1"


@pytest.mark.parametrize(
    "host",
    ["0.0.0.0", "::", "192.168.1.10", "example.com", ""],
)
def test_non_loopback_host_fails_closed(host: str) -> None:
    with pytest.raises(ConfigurationError, match="127.0.0.1"):
        resolve_bind_host(host)


def test_lan_access_feature_flag_does_not_open_the_binding() -> None:
    # Even with the (unimplemented) feature flag on, v0.1 stays loopback-only.
    with pytest.raises(ConfigurationError):
        resolve_bind_host("0.0.0.0", lan_access=True)


def test_app_exposes_the_expected_http_routes() -> None:
    # WebSocket routes are absent from OpenAPI by design; /ws/captions is
    # covered behaviourally in test_websocket.py.
    paths = set(create_app().openapi()["paths"])
    assert {
        "/api/prerequisites",
        "/api/devices",
        "/api/loopback-endpoints",
        "/api/settings",
        "/api/credentials",
        "/api/credentials/test",
        "/api/pipeline/start",
        "/api/pipeline/stop",
        "/api/pipeline/status",
    } <= paths


def test_app_does_not_enable_permissive_cors() -> None:
    app = create_app()
    middleware_names = {middleware.cls.__name__ for middleware in app.user_middleware}
    assert "CORSMiddleware" not in middleware_names
