from __future__ import annotations

import json
from typing import Any

from backend.app.audio.devices import (
    AudioDeviceBackend,
    AudioDeviceError,
    SoundDeviceBackend,
    enumerate_input_devices,
)


def build_audio_device_report(backend: AudioDeviceBackend) -> dict[str, Any]:
    devices = enumerate_input_devices(backend)
    return {
        "input_device_count": len(devices),
        "devices": [
            {
                "index": device.index,
                "name": device.name,
                "host_api": device.host_api,
                "max_input_channels": device.max_input_channels,
                "default_sample_rate": device.default_sample_rate,
                "low_input_latency_ms": round(device.low_input_latency * 1000.0, 3),
                "source_kind": device.source_kind.value,
            }
            for device in devices
        ],
    }


def main() -> int:
    try:
        report = build_audio_device_report(SoundDeviceBackend())
    except AudioDeviceError as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "ok", **report}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
