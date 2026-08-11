from __future__ import annotations

import json
from typing import Any

from backend.app.cli.serve import main


def test_serve_binds_loopback_and_reports_port() -> None:
    lines: list[str] = []
    captured: dict[str, Any] = {}

    def runner(app: Any, **kwargs: Any) -> None:
        captured.update(kwargs)
        captured["app"] = app

    exit_code = main([], emit=lines.append, runner=runner)

    assert exit_code == 0
    payload = json.loads(lines[0])
    # `ui` says whether the built page is being served: an operator who opens
    # the URL and gets a 404 needs to know the build is missing, not guess.
    assert payload["status"] == "serving"
    assert payload["host"] == "127.0.0.1"
    assert payload["port"] == 8765
    assert payload["url"] == "http://127.0.0.1:8765/"
    assert "ui" in payload
    assert captured["host"] == "127.0.0.1"


def test_serve_refuses_a_non_loopback_host() -> None:
    lines: list[str] = []

    def runner(app: Any, **kwargs: Any) -> None:  # pragma: no cover
        raise AssertionError("server must not start")

    exit_code = main(["--host", "0.0.0.0"], emit=lines.append, runner=runner)

    assert exit_code == 1
    payload = json.loads(lines[0])
    assert payload["status"] == "error"
    assert "127.0.0.1" in payload["message"]


def test_serve_reads_and_writes_the_default_user_settings_file() -> None:
    # Persistence is pointless unless the server loads the same file back on
    # the next start.
    captured: dict[str, Any] = {}
    main([], emit=lambda _line: None, runner=lambda app, **kwargs: captured.update({"app": app}))

    runtime = captured["app"].state.runtime
    assert runtime._user_settings_path is not None
    assert runtime._user_settings_path.name == "user.yaml"


def test_serve_accepts_an_explicit_port() -> None:
    lines: list[str] = []
    main([], emit=lines.append, runner=lambda app, **kwargs: None)
    default_port = json.loads(lines[0])["port"]

    lines.clear()
    main(["--port", "9100"], emit=lines.append, runner=lambda app, **kwargs: None)
    assert json.loads(lines[0])["port"] == 9100
    assert default_port != 9100


def test_serve_restores_the_saved_audio_source(monkeypatch: Any) -> None:
    # Without this the operator's saved microphone is only in the file; the
    # index it maps to has to be resolved at every start.
    calls: list[str] = []
    monkeypatch.setattr(
        "backend.app.services.runtime.PipelineRuntime.restore_audio_selection",
        lambda self: calls.append("restored"),
    )

    main([], emit=lambda _line: None, runner=lambda app, **kwargs: None)

    assert calls == ["restored"]
