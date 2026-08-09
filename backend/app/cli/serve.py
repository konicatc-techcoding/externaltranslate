from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from backend.app.api.app import create_app, resolve_bind_host
from backend.app.config import ConfigurationError, load_settings
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
    project_root = Path(__file__).resolve().parents[3]
    try:
        settings: dict[str, Any] = load_settings(
            project_root / "config" / "default.yaml", args.user_config, None
        )
        host = resolve_bind_host(args.host)
        port = args.port if args.port is not None else int(settings["server"]["port"])
        app = create_app(runtime=PipelineRuntime(settings))
    except ConfigurationError as exc:
        emit(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        return 1

    emit(
        json.dumps(
            {"status": "serving", "host": host, "port": port}, ensure_ascii=False
        )
    )
    if runner is None:  # pragma: no cover - exercised by the real server only
        import uvicorn

        runner = uvicorn.run
    runner(app, host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
