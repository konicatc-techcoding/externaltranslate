from __future__ import annotations

from typing import Any

from backend.app.cli.gemini_smoke import create_pipeline


def test_create_pipeline_wires_validated_session_rotation_seconds() -> None:
    captured: dict[str, Any] = {}
    expected = object()

    def pipeline_factory(**kwargs: Any) -> object:
        captured.update(kwargs)
        return expected

    result = create_pipeline(
        {"gemini": {"session_rotation_seconds": 480}},
        pipeline_factory=pipeline_factory,
    )

    assert result is expected
    assert captured == {"session_rotation_seconds": 480}
