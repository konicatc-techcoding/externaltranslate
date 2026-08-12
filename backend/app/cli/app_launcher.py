from __future__ import annotations

import argparse
import json
import socket
import threading
import time
import webbrowser
from collections.abc import Callable, Sequence
from typing import Any

from backend.app.cli.serve import main as serve_main

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_URL = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/"

_READY_TIMEOUT_SECONDS = 20.0
_READY_POLL_SECONDS = 0.2
_CONNECT_TIMEOUT_SECONDS = 0.5


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ExternalTranslate：啟動本機服務並開啟控制台"
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    return parser


def _port_in_use(host: str, port: int) -> bool:
    """Whether something is already listening there.

    Checked before starting rather than catching the bind error: an operator
    who double-clicks the program twice should be told it is already running,
    not shown a traceback from deep inside the server.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(_CONNECT_TIMEOUT_SECONDS)
        return probe.connect_ex((host, port)) == 0


def _wait_until_ready(
    url: str,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    timeout: float = _READY_TIMEOUT_SECONDS,
) -> bool:
    del url
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_in_use(host, port):
            return True
        time.sleep(_READY_POLL_SECONDS)
    return False


def _open_page(url: str) -> None:
    """Open the control page, ignoring whether a browser was actually found.

    `webbrowser.open` returns a bool and takes optional arguments; wrapping it
    keeps the seam a plain `(url) -> None` that a test can substitute.
    """
    webbrowser.open(url)


def _in_background(task: Callable[[], None]) -> None:
    threading.Thread(target=task, name="externaltranslate-open", daemon=True).start()


def main(
    argv: Sequence[str] | None = None,
    *,
    emit: Callable[[str], None] = print,
    serve: Callable[..., int] = serve_main,
    open_page: Callable[[str], None] = _open_page,
    wait_until_ready: Callable[..., bool] = _wait_until_ready,
    port_in_use: Callable[[str, int], bool] = _port_in_use,
    schedule: Callable[[Callable[[], None]], None] = _in_background,
) -> int:
    """Start the service and open the control page in the default browser.

    This is what a packaged build runs. There is no desktop shell: a native
    window would mean a WebView runtime the machine may not have, and this
    program does not install runtimes on anyone's behalf.
    """
    args = _parser().parse_args(argv)
    url = f"http://{DEFAULT_HOST}:{args.port}/"

    if port_in_use(DEFAULT_HOST, args.port):
        _say(
            emit,
            status="already_running",
            message=(
                f"連接埠 {args.port} 已經有服務在使用；"
                f"ExternalTranslate 可能已經在執行中。請開啟 {url}，"
                "或先關閉原本那個視窗。"
            ),
            url=url,
        )
        return 1

    if not args.no_browser:
        # Serving blocks, so the wait happens alongside it. Opening the page
        # first would show a connection error, which reads as "it failed".
        def open_when_ready() -> None:
            if wait_until_ready(url, host=DEFAULT_HOST, port=args.port):
                open_page(url)
            else:
                _say(
                    emit,
                    status="browser_skipped",
                    message=f"等待服務啟動逾時，未自動開啟瀏覽器；請手動開啟 {url}。",
                    url=url,
                )

        schedule(open_when_ready)

    return serve(["--port", str(args.port)], emit=emit)


def _say(emit: Callable[[str], None], **payload: Any) -> None:
    emit(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
