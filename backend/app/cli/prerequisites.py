from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from backend.app.config import load_settings
from backend.app.prerequisites.checker import PrerequisiteChecker
from backend.app.prerequisites.models import PrerequisiteResult


def render_report(results: Sequence[PrerequisiteResult]) -> str:
    """Render a stable UTF-8 JSON report for setup diagnostics."""

    summary = Counter(result.status.value for result in results)
    payload = {
        "階段": "Stage 0–1.2",
        "摘要": dict(summary),
        "項目": [result.to_dict() for result in results],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def render_configured_report(
    *,
    default_path: Path,
    user_path: Path | None = None,
    runtime_source_kind: str | None = None,
) -> str:
    runtime_overrides = None
    if runtime_source_kind == "input_device":
        runtime_overrides = {
            "audio": {
                "source_kind": "input_device",
                "loopback_endpoint_index": None,
            }
        }
    elif runtime_source_kind == "wasapi_loopback":
        runtime_overrides = {
            "audio": {
                "source_kind": "wasapi_loopback",
                "device_index": None,
            }
        }
    settings = load_settings(default_path, user_path, runtime_overrides)
    source_kind = str(settings["audio"]["source_kind"])
    checker = PrerequisiteChecker(enabled_audio_source=source_kind)
    return render_report(checker.stage0_report())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="檢查 ExternalTranslate Stage 0–1.2 prerequisites。"
    )
    parser.add_argument(
        "--user-config",
        type=Path,
        help="非秘密使用者 YAML 設定檔。",
    )
    parser.add_argument(
        "--source-kind",
        choices=("input_device", "wasapi_loopback"),
        help="本次檢查的runtime audio source override。",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    project_root = Path(__file__).resolve().parents[3]
    print(
        render_configured_report(
            default_path=project_root / "config" / "default.yaml",
            user_path=args.user_config,
            runtime_source_kind=args.source_kind,
        )
    )


if __name__ == "__main__":
    main()
