from __future__ import annotations

import json
from typing import Any

from backend.app.cli import app_launcher


def _run(argv: list[str], **overrides: Any) -> tuple[int, list[str], list[str]]:
    lines: list[str] = []
    events: list[str] = []
    defaults: dict[str, Any] = {
        "emit": lines.append,
        # The real launcher waits for the server on a thread because serving
        # blocks; running it inline keeps the order of events under test.
        "schedule": lambda task: task(),
        # Never probe a real port: the outcome would depend on whatever else
        # happens to be listening on this machine.
        "port_in_use": lambda _host, _port: False,
        "serve": lambda *_args, **_kwargs: events.append("serve") or 0,
        "open_page": lambda url: events.append(f"open:{url}"),
        "wait_until_ready": lambda _url, **_kwargs: events.append("ready") or True,
    }
    exit_code = app_launcher.main(argv, **{**defaults, **overrides})
    return exit_code, lines, events


def test_it_opens_the_page_only_after_the_server_is_listening() -> None:
    # Opening the browser first shows a connection error, and an operator who
    # has just double-clicked an icon reads that as "it did not work".
    exit_code, _lines, events = _run([])

    assert exit_code == 0
    assert events == ["ready", f"open:{app_launcher.DEFAULT_URL}", "serve"]


def test_a_port_already_in_use_is_explained_not_a_traceback() -> None:
    # The most likely mistake with a double-clicked program: starting it twice.
    exit_code, lines, events = _run([], port_in_use=lambda _host, _port: True)

    assert exit_code == 1
    assert events == []  # nothing started, nothing opened
    payload = json.loads(lines[-1])
    assert payload["status"] == "already_running"
    assert "已經" in payload["message"]


def test_no_browser_is_opened_when_asked_not_to() -> None:
    _exit_code, _lines, events = _run(["--no-browser"])

    assert events == ["serve"]


def test_a_server_that_never_comes_up_does_not_open_a_broken_page() -> None:
    _exit_code, lines, events = _run(
        [], wait_until_ready=lambda _url, **_kwargs: False
    )

    assert events == ["serve"]
    assert any("逾時" in line for line in lines)


def test_the_url_follows_the_port() -> None:
    _exit_code, _lines, events = _run(["--port", "9100"])

    assert "open:http://127.0.0.1:9100/" in events
