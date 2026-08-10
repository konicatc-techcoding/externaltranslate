from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app.api.app import create_app
from backend.app.audio.models import MeterReading
from backend.app.services.runtime import PipelineRuntime
from backend.app.translation.models import TranslationEvent

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

_METER = MeterReading(rms=0.1, peak=0.2, rms_dbfs=-20.0, peak_dbfs=-14.0, clipping=False)


class FakeSource:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0

    @property
    def active(self) -> bool:
        return self.started > self.stopped

    @property
    def latest_meter(self) -> MeterReading:
        return _METER

    @property
    def stats(self) -> Any:
        return None

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1

    def get_pcm_chunk(self, timeout: float) -> bytes:
        del timeout
        raise TimeoutError


class FakeSession:
    def __init__(self, events: list[TranslationEvent]) -> None:
        self._events = events
        self.release = asyncio.Event()

    async def send_audio(self, pcm_chunk: bytes) -> None:
        del pcm_chunk

    async def receive_events(self) -> AsyncIterator[TranslationEvent]:
        for event in self._events:
            yield event
        await self.release.wait()

    async def close(self) -> None:
        self.release.set()


class FakeProvider:
    def __init__(self, events: list[TranslationEvent] | None = None) -> None:
        self._events = events or []

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[FakeSession]:
        session = FakeSession(self._events)
        try:
            yield session
        finally:
            await session.close()


def make_client(
    events: list[TranslationEvent] | None = None,
    *,
    sources: list[FakeSource] | None = None,
    ws_poll_interval: float = 0.01,
) -> Iterator[TestClient]:
    created = sources if sources is not None else []

    def source_factory(_settings: Any) -> FakeSource:
        source = FakeSource()
        created.append(source)
        return source

    runtime = PipelineRuntime(
        _SETTINGS,
        source_factory=source_factory,
        provider_factory=lambda **_kwargs: FakeProvider(events),
    )
    app = create_app(runtime=runtime, ws_poll_interval=ws_poll_interval)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield from make_client()


def test_start_without_credentials_conflicts(client: TestClient) -> None:
    response = client.post("/api/pipeline/start")
    assert response.status_code == 409
    assert client.get("/api/pipeline/status").json()["running"] is False


def test_start_stop_lifecycle(client: TestClient) -> None:
    client.put("/api/credentials", json={"api_key": _KEY})

    assert client.post("/api/pipeline/start").status_code == 202
    assert client.get("/api/pipeline/status").json()["running"] is True

    assert client.post("/api/pipeline/start").status_code == 409

    assert client.post("/api/pipeline/stop").status_code == 202
    assert client.get("/api/pipeline/status").json()["running"] is False


def test_stop_without_start_is_accepted(client: TestClient) -> None:
    assert client.post("/api/pipeline/stop").status_code == 202


def test_status_shape_before_and_after_start(client: TestClient) -> None:
    idle = client.get("/api/pipeline/status").json()
    assert idle["running"] is False
    assert idle["meter"] is None
    assert idle["caption"]["status"] == "idle"
    assert {item["component"] for item in idle["components"]} == {
        "audio_source",
        "gemini_provider",
        "gemini_session",
        "caption_sink",
    }

    client.put("/api/credentials", json={"api_key": _KEY})
    client.post("/api/pipeline/start")
    running = client.get("/api/pipeline/status").json()
    assert running["running"] is True
    assert running["meter"]["peak_dbfs"] == -14.0
    client.post("/api/pipeline/stop")


def test_settings_cannot_change_while_running(client: TestClient) -> None:
    client.put("/api/credentials", json={"api_key": _KEY})
    client.post("/api/pipeline/start")

    response = client.put(
        "/api/settings",
        json={"source_kind": "input_device", "device_index": 1, "channel": 1},
    )
    assert response.status_code == 409

    client.post("/api/pipeline/stop")


def test_start_reports_why_the_audio_source_could_not_be_built() -> None:
    from backend.app.audio.devices import AudioDeviceError

    def failing_factory(_settings: Any) -> FakeSource:
        raise AudioDeviceError("尚未選擇 audio.device_index，無法啟動輸入裝置。")

    runtime = PipelineRuntime(
        _SETTINGS,
        source_factory=failing_factory,
        provider_factory=lambda **_kwargs: FakeProvider(),
    )
    with TestClient(create_app(runtime=runtime)) as client:
        client.put("/api/credentials", json={"api_key": _KEY})
        response = client.post("/api/pipeline/start")

    # A generic 503 would leave the user with nothing to act on.
    assert response.status_code == 422
    assert "device_index" in response.json()["detail"]


def test_restart_leaves_no_source_behind() -> None:
    sources: list[FakeSource] = []
    for client in make_client(sources=sources):
        client.put("/api/credentials", json={"api_key": _KEY})
        client.post("/api/pipeline/start")
        client.post("/api/pipeline/stop")
        client.post("/api/pipeline/start")
        client.post("/api/pipeline/stop")

    assert len(sources) == 2
    assert [source.started for source in sources] == [1, 1]
    assert [source.stopped for source in sources] == [1, 1]
