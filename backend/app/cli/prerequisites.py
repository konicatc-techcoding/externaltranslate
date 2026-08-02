from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence

from backend.app.prerequisites.checker import PrerequisiteChecker
from backend.app.prerequisites.models import PrerequisiteResult


def render_report(results: Sequence[PrerequisiteResult]) -> str:
    """Render a stable UTF-8 JSON report for setup diagnostics."""

    summary = Counter(result.status.value for result in results)
    payload = {
        "階段": "Stage 0",
        "摘要": dict(summary),
        "項目": [result.to_dict() for result in results],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def main() -> None:
    print(render_report(PrerequisiteChecker().stage0_report()))


if __name__ == "__main__":
    main()
