from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from backend.app.api.dependencies import (
    DeviceLister,
    LoopbackLister,
    PrerequisiteReporter,
    get_device_lister,
    get_loopback_lister,
    get_prerequisite_reporter,
    get_runtime,
)
from backend.app.api.routes import (
    captions,
    catalog,
    credentials,
    pipeline,
    presets,
    settings,
    vmix,
)
from backend.app.api.websocket import DEFAULT_POLL_INTERVAL
from backend.app.api.websocket import router as websocket_router
from backend.app.audio.devices import SoundDeviceBackend, enumerate_input_devices
from backend.app.audio.models import AudioDeviceInfo, LoopbackEndpointInfo
from backend.app.config import ConfigurationError, load_settings
from backend.app.prerequisites.checker import PrerequisiteChecker
from backend.app.prerequisites.models import PrerequisiteResult
from backend.app.services.runtime import PipelineRuntime

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def resolve_bind_host(host: str | None, *, lan_access: bool = False) -> str:
    """Return the only host v0.1 is allowed to bind to.

    LAN exposure would put a local translation service — and the audio it can
    hear — on the network, so a non-loopback host fails closed even when the
    (still unimplemented) `features.lan_access` flag is set.
    """
    if host is None:
        return "127.0.0.1"
    if host in _LOOPBACK_HOSTS:
        return "127.0.0.1"
    del lan_access  # deliberately ignored in v0.1
    raise ConfigurationError(
        f"本機服務只允許綁定 127.0.0.1，不接受 {host!r}。"
    )


def _default_settings() -> dict[str, object]:
    project_root = Path(__file__).resolve().parents[3]
    return load_settings(project_root / "config" / "default.yaml", None, None)


def _default_prerequisites() -> list[PrerequisiteResult]:
    return PrerequisiteChecker().stage0_report()


def _default_devices() -> list[AudioDeviceInfo]:
    return enumerate_input_devices(SoundDeviceBackend())


def _default_loopback_endpoints() -> list[LoopbackEndpointInfo]:
    from backend.app.audio.sources.wasapi_loopback import enumerate_loopback_endpoints

    return enumerate_loopback_endpoints()


def create_app(
    *,
    runtime: PipelineRuntime | None = None,
    prerequisite_reporter: PrerequisiteReporter | None = None,
    device_lister: DeviceLister | None = None,
    loopback_lister: LoopbackLister | None = None,
    ws_poll_interval: float = DEFAULT_POLL_INTERVAL,
) -> FastAPI:
    """Build the local-only control API.

    No CORS middleware is installed: the UI is served from the same origin,
    and an open CORS policy would let any page in the browser drive the local
    pipeline.
    """
    app = FastAPI(title="ExternalTranslate", version="0.1.0")
    active_runtime = runtime or PipelineRuntime(_default_settings())

    app.state.runtime = active_runtime
    app.state.ws_poll_interval = ws_poll_interval

    app.dependency_overrides[get_runtime] = lambda: active_runtime
    app.dependency_overrides[get_prerequisite_reporter] = (
        lambda: prerequisite_reporter or _default_prerequisites
    )
    app.dependency_overrides[get_device_lister] = (
        lambda: device_lister or _default_devices
    )
    app.dependency_overrides[get_loopback_lister] = (
        lambda: loopback_lister or _default_loopback_endpoints
    )

    app.include_router(captions.router)
    app.include_router(catalog.router)
    app.include_router(presets.router)
    app.include_router(settings.router)
    app.include_router(credentials.router)
    app.include_router(pipeline.router)
    app.include_router(vmix.router)
    app.include_router(websocket_router)
    return app
