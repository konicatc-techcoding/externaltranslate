from __future__ import annotations

import time

from backend.app.translation.models import TranslationEvent, TranslationEventKind
from backend.tests.api.test_pipeline_route import make_client

_KEY = "AIzaSyFAKEKEYFAKEKEYFAKEKEY"


def _caption_event(text: str, *, finished: bool = False) -> TranslationEvent:
    return TranslationEvent(
        kind=TranslationEventKind.OUTPUT_TRANSCRIPTION,
        text=text,
        language_code="zh-Hant",
        finished=finished,
    )


def test_socket_sends_a_snapshot_immediately_on_connect() -> None:
    for client in make_client():
        with client.websocket_connect("/ws/captions") as socket:
            first = socket.receive_json()
    assert first["running"] is False
    assert first["caption"]["status"] == "idle"
    assert first["meter"] is None


def test_socket_pushes_caption_updates() -> None:
    events = [_caption_event("你好"), _caption_event("嗎？", finished=True)]
    for client in make_client(events):
        client.put("/api/credentials", json={"api_key": _KEY})
        with client.websocket_connect("/ws/captions") as socket:
            socket.receive_json()  # initial snapshot
            client.post("/api/pipeline/start")

            texts: list[str] = []
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                payload = socket.receive_json()
                text = payload["caption"]["text"]
                if text and (not texts or texts[-1] != text):
                    texts.append(text)
                if payload["caption"]["status"] == "final":
                    break
            client.post("/api/pipeline/stop")

    assert texts[-1] == "你好嗎？"


def test_socket_payload_never_contains_the_api_key() -> None:
    for client in make_client([_caption_event("你好")]):
        client.put("/api/credentials", json={"api_key": _KEY})
        with client.websocket_connect("/ws/captions") as socket:
            client.post("/api/pipeline/start")
            seen = [socket.receive_json() for _ in range(3)]
            client.post("/api/pipeline/stop")

    assert all(_KEY not in str(payload) for payload in seen)
    assert all("api_key" not in str(payload) for payload in seen)


def test_two_sockets_receive_the_same_snapshot() -> None:
    for client in make_client():
        with (
            client.websocket_connect("/ws/captions") as first,
            client.websocket_connect("/ws/captions") as second,
        ):
            assert first.receive_json() == second.receive_json()


def test_socket_reports_running_state_transitions() -> None:
    for client in make_client():
        client.put("/api/credentials", json={"api_key": _KEY})
        with client.websocket_connect("/ws/captions") as socket:
            assert socket.receive_json()["running"] is False
            client.post("/api/pipeline/start")

            deadline = time.monotonic() + 3.0
            running_seen = False
            while time.monotonic() < deadline and not running_seen:
                running_seen = socket.receive_json()["running"]
            client.post("/api/pipeline/stop")

    assert running_seen is True


def test_client_messages_do_not_control_the_pipeline() -> None:
    for client in make_client():
        client.put("/api/credentials", json={"api_key": _KEY})
        with client.websocket_connect("/ws/captions") as socket:
            socket.receive_json()
            socket.send_json({"action": "start"})
            time.sleep(0.05)
            assert client.get("/api/pipeline/status").json()["running"] is False
