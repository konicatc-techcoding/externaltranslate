from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.audio.sources.input_device import AudioCaptureError
from backend.app.audio.sources.wasapi_loopback import (
    LoopbackCaptureError,
    LoopbackDeviceError,
    WasapiLoopbackSource,
)
from backend.app.cli.audio_smoke import run_smoke_capture


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ExternalTranslate Windows WASAPI system-output loopback smoke test"
    )
    parser.add_argument(
        "--endpoint-index",
        type=int,
        help="省略時於每次 Start 使用當下 Windows default output。",
    )
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    source = WasapiLoopbackSource(endpoint_index=args.endpoint_index)
    initial_selection = None

    def remember_initial_selection() -> None:
        nonlocal initial_selection
        initial_selection = source.selection

    try:
        report = run_smoke_capture(
            source,
            duration_seconds=args.duration,
            output_path=args.output,
            capture_started=remember_initial_selection,
        )
        selection = initial_selection
        if selection is None:
            raise LoopbackCaptureError("WASAPI loopback 沒有已解析的 endpoint。")
        endpoint = selection.endpoint
        result = {
            "status": "ok",
            "endpoint": {
                "index": endpoint.index,
                "name": endpoint.name,
                "host_api": endpoint.host_api,
                "channels": endpoint.channels,
                "native_sample_rate": selection.native_format.sample_rate,
                "is_default": endpoint.is_default,
            },
            **report,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (
        AudioCaptureError,
        LoopbackCaptureError,
        LoopbackDeviceError,
        ValueError,
    ) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
