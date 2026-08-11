from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app.api.app import create_app
from backend.app.services.runtime import PipelineRuntime
from backend.tests.outputs.fake_vmix import FakeInput, FakeVmix

_TITLE = FakeInput(
    guid="877bb3e7-58bd-46a1-85ce-0d673aec6bf5",
    number=1,
    name="字幕標題",
    text_fields=("Line1.Text", "Line2.Text"),
)


def _settings(port: int) -> dict[str, Any]:
    return {
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
        "vmix": {
            "host": "127.0.0.1",
            "port": port,
            "input_guid": _TITLE.guid,
            "input_name": "字幕標題",
            "fields": ["Line1.Text", "Line2.Text"],
            "min_interval_ms": 200,
            "timeout_ms": 500,
        },
        "features": {"vmix_output": False},
    }


@pytest.fixture
def server() -> Iterator[FakeVmix]:
    with FakeVmix([_TITLE]) as running:
        yield running


@pytest.fixture
def client(server: FakeVmix) -> Iterator[TestClient]:
    runtime = PipelineRuntime(
        _settings(server.port),
        source_factory=lambda _settings: pytest.fail("source must not be built"),
        provider_factory=lambda **_kwargs: pytest.fail("provider must not be built"),
        device_lister=lambda: [],
        loopback_lister=lambda: [],
    )
    with TestClient(create_app(runtime=runtime)) as test_client:
        yield test_client


def test_inputs_are_listed_with_their_field_names(client: TestClient) -> None:
    body = client.get("/api/vmix/inputs").json()

    assert body["inputs"][0]["guid"] == _TITLE.guid
    assert body["inputs"][0]["name"] == "字幕標題"
    # The operator needs these to build the title in vMix.
    assert body["inputs"][0]["text_fields"] == ["Line1.Text", "Line2.Text"]


def test_vmix_being_down_is_503_not_a_crash(
    client: TestClient, server: FakeVmix
) -> None:
    server.set_mode("close")

    assert client.get("/api/vmix/inputs").status_code == 503
    assert client.post("/api/vmix/test", json={}).status_code == 503


def test_settings_round_trip(client: TestClient) -> None:
    response = client.put(
        "/api/settings/vmix",
        json={"enabled": True, "fields": ["A.Text", "B.Text", "C.Text"]},
    )

    assert response.status_code == 200
    vmix = response.json()["vmix"]
    assert vmix["enabled"] is True
    assert vmix["fields"] == ["A.Text", "B.Text", "C.Text"]


def test_invalid_settings_are_refused_and_change_nothing(client: TestClient) -> None:
    before = client.get("/api/settings").json()["vmix"]

    for payload in (
        {"host": "http://192.168.1.2:8088"},
        {"fields": []},
        {"port": 0},
        {"min_interval_ms": 5},
        {"unknown": 1},
    ):
        assert client.put("/api/settings/vmix", json=payload).status_code == 422

    assert client.get("/api/settings").json()["vmix"] == before


def test_a_remote_host_is_accepted(client: TestClient) -> None:
    # vMix on another machine is supported; the UI carries the plaintext
    # warning rather than the API refusing it.
    response = client.put("/api/settings/vmix", json={"host": "192.168.1.50"})

    assert response.status_code == 200
    assert response.json()["vmix"]["host"] == "192.168.1.50"


def test_the_settings_payload_carries_no_credential(client: TestClient) -> None:
    body = client.get("/api/settings").text
    assert "password" not in body.lower()


def test_collapsed_panels_round_trip(client: TestClient) -> None:
    # Folding a panel away is a setting like any other, so it goes to the
    # settings file rather than to browser storage.
    response = client.put(
        "/api/settings/ui", json={"collapsed": ["prerequisites", "vmix"]}
    )

    assert response.status_code == 200
    assert response.json()["ui"]["collapsed"] == ["prerequisites", "vmix"]
    assert client.get("/api/settings").json()["ui"]["collapsed"] == [
        "prerequisites",
        "vmix",
    ]


def test_an_unknown_panel_id_is_refused(client: TestClient) -> None:
    response = client.put("/api/settings/ui", json={"collapsed": ["nonsense"]})

    assert response.status_code == 422
    assert client.get("/api/settings").json()["ui"]["collapsed"] == []


def test_the_test_caption_writes_every_field_in_order(
    client: TestClient, server: FakeVmix
) -> None:
    # One marker per field, so a title whose boxes are in the wrong order
    # shows it immediately.
    response = client.post("/api/vmix/test", json={})

    assert response.status_code == 200
    written = [(call.field, call.value) for call in server.calls]
    assert written == [
        ("Line1.Text", "第 1 行（Line1.Text）"),
        ("Line2.Text", "第 2 行（Line2.Text）"),
    ]
    assert response.json()["lines"] == [
        "第 1 行（Line1.Text）",
        "第 2 行（Line2.Text）",
    ]


def test_custom_test_lines_pad_the_unused_fields(
    client: TestClient, server: FakeVmix
) -> None:
    # A one-line caption must blank the second field, exactly as a real run
    # does — otherwise the previous line stays under the new one.
    response = client.post("/api/vmix/test", json={"lines": ["只有一行"]})

    assert response.status_code == 200
    assert [call.value for call in server.calls] == ["只有一行", ""]


def test_clearing_blanks_every_field(client: TestClient, server: FakeVmix) -> None:
    client.post("/api/vmix/test", json={})
    server.state.calls.clear()

    response = client.post("/api/vmix/clear")

    assert response.status_code == 200
    assert [call.value for call in server.calls] == ["", ""]


def test_a_test_without_a_chosen_input_is_422(client: TestClient) -> None:
    client.put("/api/settings/vmix", json={"input_guid": None, "input_name": None})

    assert client.post("/api/vmix/test", json={}).status_code == 422


def test_the_chosen_input_can_be_cleared(client: TestClient) -> None:
    # An explicit null means "deselect". Treating it as "not provided" would
    # make the panel's "—" option silently do nothing.
    response = client.put(
        "/api/settings/vmix", json={"input_guid": None, "input_name": None}
    )

    assert response.status_code == 200
    assert response.json()["vmix"]["input_guid"] is None
