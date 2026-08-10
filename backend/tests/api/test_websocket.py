from __future__ import annotations

import time

import pytest
from starlette.websockets import WebSocketDisconnect

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


def test_appearance_and_layout_changes_are_pushed() -> None:
    # Appearance deliberately does not touch the caption revision (it does not
    # reflow anything), so unless the push key covers it the control page and
    # every overlay would keep showing the old style. Asserted on the key
    # rather than through the socket: a missing push blocks receive_json()
    # forever instead of failing.
    from backend.app.api.websocket import _push_key

    for client in make_client():
        runtime = client.app.state.runtime  # type: ignore[attr-defined]

        before = _push_key(runtime.snapshot())
        runtime.update_caption_style({"font": "kai", "size": 72, "color": "#FF0000"})
        assert _push_key(runtime.snapshot()) != before

        # An outline changes nothing about the text or the layout, so it is
        # exactly the kind of change a revision-based key would drop.
        before = _push_key(runtime.snapshot())
        runtime.update_caption_style({"outline_width": 4})
        after_style = _push_key(runtime.snapshot())
        assert after_style != before

        runtime.update_caption_layout(
            chars_per_line=8, max_lines=3, sentence_breaks=True
        )
        assert _push_key(runtime.snapshot()) != after_style


def test_only_loopback_origins_may_connect() -> None:
    for client in make_client():
        for origin in ("http://localhost:5173", "http://127.0.0.1:8765"):
            with client.websocket_connect(
                "/ws/captions", headers={"origin": origin}
            ) as socket:
                assert socket.receive_json()["running"] is False

        for origin in ("https://evil.example", "http://192.168.1.10:5173"):
            with pytest.raises(WebSocketDisconnect) as caught, client.websocket_connect(
                "/ws/captions", headers={"origin": origin}
            ) as socket:
                socket.receive_json()
            assert caught.value.code == 1008


def test_disconnect_ends_the_server_side_loop() -> None:
    # An idle socket that is never written to must still notice the client
    # leaving, otherwise every reconnect leaks a task writing to a dead peer.
    for client in make_client(ws_poll_interval=0.01):
        with client.websocket_connect("/ws/captions") as socket:
            socket.receive_json()
        # A second connection on the same app proves the first one released.
        with client.websocket_connect("/ws/captions") as socket:
            assert socket.receive_json()["running"] is False


def test_client_messages_do_not_control_the_pipeline() -> None:
    for client in make_client():
        client.put("/api/credentials", json={"api_key": _KEY})
        with client.websocket_connect("/ws/captions") as socket:
            socket.receive_json()
            socket.send_json({"action": "start"})
            time.sleep(0.05)
            assert client.get("/api/pipeline/status").json()["running"] is False
