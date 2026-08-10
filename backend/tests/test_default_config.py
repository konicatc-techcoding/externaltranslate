from __future__ import annotations

from pathlib import Path

from backend.app.config import load_settings


def test_project_default_config_is_non_secret_and_loopback_only() -> None:
    project_root = Path(__file__).resolve().parents[2]

    settings = load_settings(project_root / "config" / "default.yaml")

    assert settings["server"]["host"] == "127.0.0.1"
    assert settings["gemini"]["model"] == "gemini-3.5-live-translate-preview"
    assert settings["gemini"]["target_language_code"] == "zh-Hant"
    assert settings["caption"]["max_payload_length"] == 4096
    assert settings["audio"] == {
        "source_kind": "input_device",
        "device_index": None,
        "device_name": None,
        "device_host_api": None,
        "loopback_endpoint_index": None,
        "loopback_endpoint_name": None,
        "channel": 1,
        "target_sample_rate": 16000,
        "chunk_duration_ms": 100,
        "raw_queue_capacity": 32,
        "pcm_queue_capacity": 50,
    }
