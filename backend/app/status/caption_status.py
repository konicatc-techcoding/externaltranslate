from __future__ import annotations

from backend.app.captions.models import CaptionState, CaptionStatus
from backend.app.status.models import Component, ComponentState, StatusReason
from backend.app.status.publisher import StatusPublisher

# The status package may depend on captions, never the other way round: this
# keeps `backend.app.captions` free of observability concerns while giving
# every composition root (CLI, API runtime) one shared mapping.
CAPTION_SINK_STATES: dict[CaptionStatus, tuple[ComponentState, StatusReason]] = {
    CaptionStatus.PARTIAL: (ComponentState.ACTIVE, StatusReason.PARTIAL),
    CaptionStatus.FINAL: (ComponentState.ACTIVE, StatusReason.FINAL),
    CaptionStatus.IDLE: (ComponentState.RESET, StatusReason.RESET),
}


def publish_caption_status(publisher: StatusPublisher, state: CaptionState) -> None:
    """Report a caption state change as component status, metadata only."""
    component_state, reason = CAPTION_SINK_STATES[state.status]
    publisher.publish(
        Component.CAPTION_SINK,
        component_state,
        reason=reason,
        generation=state.session_generation,
        text_length=len(state.text),
    )
