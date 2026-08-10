from __future__ import annotations

from backend.app.api.models import (
    CaptionLayout,
    CaptionPayload,
    CaptionStyle,
    ComponentStatusItem,
    MeterPayload,
    RuntimeStatusResponse,
)
from backend.app.services.runtime import RuntimeSnapshot


def runtime_status_response(snapshot: RuntimeSnapshot) -> RuntimeStatusResponse:
    """Serialize a runtime snapshot for HTTP and WebSocket consumers.

    Every field here comes from an already-sanitized source: caption text is
    control-character free and length bounded, component detail is composed
    from the status whitelist, and the API key has no path into this shape.
    """
    caption = snapshot.caption
    meter = snapshot.meter
    return RuntimeStatusResponse(
        running=snapshot.running,
        layout=CaptionLayout(
            chars_per_line=snapshot.layout[0], max_lines=snapshot.layout[1]
        ),
        style=CaptionStyle(**snapshot.style),
        elapsed_seconds=snapshot.elapsed_seconds,
        status_revision=snapshot.status.revision,
        components=[
            ComponentStatusItem(
                component=status.component.value,
                state=status.state.value,
                detail=status.detail,
                revision=status.revision,
                session_generation=status.session_generation,
                updated_at=status.updated_at,
            )
            for status in snapshot.status.statuses
        ],
        caption=CaptionPayload(
            revision=caption.revision,
            status=caption.status.value,
            text=caption.text,
            lines=list(caption.lines),
            language_code=caption.language_code,
            updated_at=caption.updated_at,
            session_generation=caption.session_generation,
        ),
        meter=None
        if meter is None
        else MeterPayload(
            rms=meter.rms,
            peak=meter.peak,
            rms_dbfs=meter.rms_dbfs,
            peak_dbfs=meter.peak_dbfs,
            clipping=meter.clipping,
        ),
        last_error=snapshot.last_error,
        audio_notice=snapshot.audio_notice,
    )
