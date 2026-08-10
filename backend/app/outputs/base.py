from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class CaptionOutput(Protocol):
    """Somewhere caption lines are sent, besides the web overlay.

    The pipeline knows only this shape, so vMix stays one implementation
    rather than a branch inside the caption path. Nothing here may raise:
    an output that is unreachable is a normal condition, not an error the
    translation has to handle.
    """

    def publish(self, lines: Sequence[str]) -> None:
        """Offer the newest caption lines. Returns immediately."""

    async def clear(self) -> None:
        """Blank whatever is on screen, now.

        Called when translation stops or captions are cleared. Without it the
        last sentence stays on the vMix title forever, which reads as
        translation still running.
        """

    async def aclose(self) -> None:
        """Release the output."""


class NullOutput:
    """The output used when vMix is switched off: does nothing, costs nothing."""

    def publish(self, lines: Sequence[str]) -> None:
        del lines

    async def clear(self) -> None:
        return

    async def aclose(self) -> None:
        return
