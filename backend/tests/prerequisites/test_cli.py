from __future__ import annotations

import json

from backend.app.cli.prerequisites import render_report
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
                label="音訊輸入裝置與驅動",
                status=PrerequisiteStatus.NOT_CHECKED,
                required_for="Stage 1",
                action="Stage 1 再檢查。",
            ),
        ]
    )

    payload = json.loads(output)
    assert payload["階段"] == "Stage 0"
    assert payload["摘要"] == {"ready": 1, "not_checked": 1}
    assert payload["項目"][1]["label"] == "音訊輸入裝置與驅動"
    assert "\\u97f3" not in output
