from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from backend.app.api.app import create_app, resolve_bind_host
from backend.app.config import ConfigurationError, load_settings
from backend.app.resources import default_settings_path, user_settings_path
from backend.app.services.runtime import PipelineRuntime


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ExternalTranslate 本機控制服務（只綁定 127.0.0.1）"
    )
    parser.add_argument("--user-config", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=None)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    emit: Callable[[str], None] = print,
    runner: Callable[..., None] | None = None,
) -> int:
    args = _parser().parse_args(argv)
    try:
        # Settings the operator changed last time live here; the same file
        # is what they copy to move a setup to another machine. In a
        # packaged build it lives under %LOCALAPPDATA%, not beside the
        # program, which may be installed somewhere read-only.
        user_config = args.user_config or user_settings_path()
        settings: dict[str, Any] = load_settings(
            default_settings_path(), user_config, None
        )
        host = resolve_bind_host(args.host)
        port = args.port if args.port is not None else int(settings["server"]["port"])
        runtime = PipelineRuntime(settings, user_settings_path=user_config)
        # The file remembers the device by name; the index it has on this
        # machine, right now, can only be resolved here.
        runtime.restore_audio_selection()
        app = create_app(runtime=runtime)
    except ConfigurationError as exc:
        emit(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        return 1

    served = app.state.frontend_dist
    emit(
        json.dumps(
            {
                "status": "serving",
                "host": host,
                "port": port,
                "url": f"http://{host}:{port}/",
                # None means the frontend has not been built in this checkout;
                # the API works but the page will 404, and the operator should
                # be told that rather than left guessing.
                "ui": None if served is None else str(served),
            },
            ensure_ascii=False,
        )
    )
    if runner is None:  # pragma: no cover - exercised by the real server only
        import uvicorn

        runner = uvicorn.run
    runner(app, host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
