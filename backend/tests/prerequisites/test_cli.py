from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.cli.prerequisites import render_configured_report, render_report
from backend.app.prerequisites.models import PrerequisiteResult, PrerequisiteStatus


def test_render_report_outputs_utf8_json_with_summary() -> None:
    output = render_report(
        [
            PrerequisiteResult(
                identifier="python",
                label="Python",
                status=PrerequisiteStatus.READY,
                required_for="Stage 0",
                version="3.11.0",
                detail="已安裝。",
            ),
            PrerequisiteResult(
                identifier="audio",
                label="音訊輸入裝置與 PortAudio",
                status=PrerequisiteStatus.READY,
                required_for="Stage 1",
            ),
        ]
    )

    payload = json.loads(output)
    assert payload["階段"] == "Stage 0–1.2"
    assert payload["摘要"] == {"ready": 2}
    assert payload["項目"][1]["label"] == "音訊輸入裝置與 PortAudio"
    assert "\\u97f3" not in output


def test_render_configured_report_passes_enabled_source_to_checker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    default_path = tmp_path / "default.yaml"
    default_path.write_text(
        "audio:\n"
        "  source_kind: input_device\n"
        "  device_index: null\n"
        "  loopback_endpoint_index: null\n"
        "  channel: 1\n"
        "  target_sample_rate: 16000\n"
        "  chunk_duration_ms: 100\n"
        "  raw_queue_capacity: 32\n"
        "  pcm_queue_capacity: 50\n",
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    class FakeChecker:
        def __init__(self, *, enabled_audio_source: str) -> None:
            captured["enabled_audio_source"] = enabled_audio_source

        def stage0_report(self) -> list[PrerequisiteResult]:
            return []

    monkeypatch.setattr(
        "backend.app.cli.prerequisites.PrerequisiteChecker", FakeChecker
    )

    payload = json.loads(render_configured_report(default_path=default_path))

    assert captured == {"enabled_audio_source": "input_device"}
    assert payload["摘要"] == {}


def test_render_configured_report_applies_user_and_runtime_source_priority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    default_path = tmp_path / "default.yaml"
    user_path = tmp_path / "user.yaml"
    default_path.write_text(
        "audio:\n"
        "  source_kind: input_device\n"
        "  device_index: null\n"
        "  loopback_endpoint_index: null\n"
        "  channel: 1\n"
        "  target_sample_rate: 16000\n"
        "  chunk_duration_ms: 100\n"
        "  raw_queue_capacity: 32\n"
        "  pcm_queue_capacity: 50\n",
        encoding="utf-8",
    )
    user_path.write_text(
        "audio:\n"
        "  source_kind: wasapi_loopback\n"
        "  loopback_endpoint_index: 9\n",
        encoding="utf-8",
    )
    captured: list[str] = []

    class FakeChecker:
        def __init__(self, *, enabled_audio_source: str) -> None:
            captured.append(enabled_audio_source)

        def stage0_report(self) -> list[PrerequisiteResult]:
            return []

    monkeypatch.setattr(
        "backend.app.cli.prerequisites.PrerequisiteChecker", FakeChecker
    )

    render_configured_report(default_path=default_path, user_path=user_path)
    render_configured_report(
        default_path=default_path,
        user_path=user_path,
        runtime_source_kind="input_device",
    )

    assert captured == ["wasapi_loopback", "input_device"]


def test_runtime_loopback_override_clears_user_input_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    default_path = tmp_path / "default.yaml"
    user_path = tmp_path / "user.yaml"
    default_path.write_text(
        "audio:\n"
        "  source_kind: input_device\n"
        "  device_index: null\n"
        "  loopback_endpoint_index: null\n"
        "  channel: 1\n"
        "  target_sample_rate: 16000\n"
        "  chunk_duration_ms: 100\n"
        "  raw_queue_capacity: 32\n"
        "  pcm_queue_capacity: 50\n",
        encoding="utf-8",
    )
    user_path.write_text(
        "audio:\n"
        "  source_kind: input_device\n"
        "  device_index: 7\n",
        encoding="utf-8",
    )
    captured: list[str] = []

    class FakeChecker:
        def __init__(self, *, enabled_audio_source: str) -> None:
            captured.append(enabled_audio_source)

        def stage0_report(self) -> list[PrerequisiteResult]:
            return []

    monkeypatch.setattr(
        "backend.app.cli.prerequisites.PrerequisiteChecker", FakeChecker
    )

    render_configured_report(
        default_path=default_path,
        user_path=user_path,
        runtime_source_kind="wasapi_loopback",
    )

    assert captured == ["wasapi_loopback"]
