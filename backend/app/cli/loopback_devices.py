from __future__ import annotations

import json
from typing import Any

from backend.app.audio.sources.wasapi_loopback import (
    LoopbackDeviceBackend,
    LoopbackDeviceError,
    PyAudioWPatchDeviceBackend,
    enumerate_loopback_endpoints,
)


def build_loopback_endpoint_report(backend: LoopbackDeviceBackend) -> dict[str, Any]:
    endpoints = enumerate_loopback_endpoints(backend)
    return {
        "loopback_endpoint_count": len(endpoints),
        "endpoints": [
            {
                "index": endpoint.index,
                "name": endpoint.name,
                "host_api": endpoint.host_api,
                "channels": endpoint.channels,
                "default_sample_rate": endpoint.default_sample_rate,
                "low_input_latency_ms": round(endpoint.low_input_latency * 1000.0, 3),
                "is_default": endpoint.is_default,
                "source_kind": endpoint.source_kind.value,
            }
            for endpoint in endpoints
        ],
    }


def main() -> int:
    try:
        report = build_loopback_endpoint_report(PyAudioWPatchDeviceBackend())
    except LoopbackDeviceError as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "ok", **report}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
