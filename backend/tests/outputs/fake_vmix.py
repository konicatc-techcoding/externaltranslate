"""A stand-in for vMix's Web API, served over a real TCP socket.

Unit tests with an injected transport never exercise percent-encoding, socket
errors or timeouts — which is where an HTTP integration actually breaks. This
serves the same shapes vMix documents so those paths run for real.

It is *not* a substitute for acceptance: it was written from the docs, so it
can only prove that we send what the docs describe. Whether vMix renders it
the way we expect is Phase B, on real hardware.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType
from typing import Literal
from urllib.parse import parse_qs, urlparse

Mode = Literal["ok", "slow", "server_error", "not_found", "garbage", "close"]


@dataclass
class SetTextCall:
    input: str
    field: str
    value: str


@dataclass
class FakeInput:
    guid: str
    number: int
    name: str
    text_fields: tuple[str, ...] = ()
    kind: str = "GT"


@dataclass
class FakeVmixState:
    inputs: list[FakeInput] = field(default_factory=list)
    calls: list[SetTextCall] = field(default_factory=list)
    mode: Mode = "ok"
    slow_seconds: float = 2.0


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _state_xml(state: FakeVmixState) -> bytes:
    parts = ["<vmix><version>28.0.0.42</version><inputs>"]
    for item in state.inputs:
        parts.append(
            f'<input key="{_xml_escape(item.guid)}" number="{item.number}" '
            f'type="{_xml_escape(item.kind)}" title="{_xml_escape(item.name)}" '
            f'shortTitle="{_xml_escape(item.name)}" state="Paused">'
        )
        for index, name in enumerate(item.text_fields):
            parts.append(f'<text index="{index}" name="{_xml_escape(name)}"></text>')
        parts.append("</input>")
    parts.append("</inputs></vmix>")
    return "".join(parts).encode("utf-8")


class _Handler(BaseHTTPRequestHandler):
    state: FakeVmixState

    def log_message(self, *_args: object) -> None:  # keep test output clean
        return

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        state = self.state
        if state.mode == "slow":
            time.sleep(state.slow_seconds)
        if state.mode == "close":
            self.close_connection = True
            return
        if state.mode == "server_error":
            self.send_error(500, "boom")
            return
        if state.mode == "not_found":
            self.send_error(404, "no such input")
            return

        parsed = urlparse(self.path)
        query = parse_qs(parsed.query, keep_blank_values=True)
        function = (query.get("Function") or [""])[0]

        if state.mode == "garbage":
            self._respond(b"<vmix><inputs>" + b"\xff\xfe not xml")
            return

        if function == "":
            self._respond(_state_xml(state))
            return

        if function == "SetText":
            state.calls.append(
                SetTextCall(
                    input=(query.get("Input") or [""])[0],
                    field=(query.get("SelectedName") or [""])[0],
                    value=(query.get("Value") or [""])[0],
                )
            )
            self._respond(b"Function completed successfully")
            return

        self.send_error(400, "unsupported function")

    def _respond(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/xml; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class FakeVmix:
    """Context manager serving the fake on a free loopback port."""

    def __init__(self, inputs: list[FakeInput] | None = None) -> None:
        self.state = FakeVmixState(inputs=list(inputs or []))
        handler = type("_BoundHandler", (_Handler,), {"state": self.state})
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        # Otherwise a connection left open by the "close" mode keeps a
        # non-daemon thread alive past the test and pytest reports it.
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def host(self) -> str:
        return "127.0.0.1"

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    @property
    def calls(self) -> list[SetTextCall]:
        return self.state.calls

    def set_mode(self, mode: Mode) -> None:
        self.state.mode = mode

    def __enter__(self) -> FakeVmix:
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
