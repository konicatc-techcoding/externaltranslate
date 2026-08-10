from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from backend.app.audio.models import AudioDeviceInfo, LoopbackEndpointInfo


@dataclass(frozen=True, slots=True)
class ResolvedIndex:
    """An enumeration index recovered from a saved device identity.

    ``index`` is ``None`` whenever the saved device cannot be identified
    beyond doubt, and ``notice`` then explains why in Traditional Chinese.
    Leaving the selection empty is the whole point: an enumeration index is a
    position in a list, not an identity, so restoring one after a replug,
    a reboot or a move to another machine can silently open different
    hardware. Nothing here guesses.
    """

    index: int | None
    notice: str | None = None


def resolve_device_index(
    devices: Sequence[AudioDeviceInfo],
    *,
    name: str | None,
    host_api: str | None,
) -> ResolvedIndex:
    """Find the input device the operator chose last time, by name."""
    if not name:
        return ResolvedIndex(index=None)

    matches = [item for item in devices if item.name == name]
    if host_api:
        exact = [item for item in matches if item.host_api == host_api]
        # A driver reinstall can move a device between host APIs. Falling back
        # to the name is safe as long as the name is still unambiguous.
        if exact:
            matches = exact

    if not matches:
        return ResolvedIndex(
            index=None,
            notice=(
                f"找不到上次使用的音訊裝置「{name}」，已改為未選擇；請重新選擇音訊來源。"
            ),
        )
    if len(matches) > 1:
        return ResolvedIndex(
            index=None,
            notice=(
                f"偵測到多個名稱相同的音訊裝置「{name}」，無法判斷是哪一個，"
                "已改為未選擇；請重新選擇音訊來源。"
            ),
        )
    return ResolvedIndex(index=matches[0].index)


def resolve_endpoint_index(
    endpoints: Sequence[LoopbackEndpointInfo], *, name: str | None
) -> ResolvedIndex:
    """Find the loopback endpoint chosen last time, by name.

    ``None`` is a meaningful selection here — it means "whatever Windows is
    playing to right now" — so a missing endpoint degrades to the default
    output rather than to a broken configuration.
    """
    if not name:
        return ResolvedIndex(index=None)

    matches = [item for item in endpoints if item.name == name]
    if not matches:
        return ResolvedIndex(
            index=None,
            notice=(
                f"找不到上次使用的系統音源「{name}」，已改用 Windows 目前的預設輸出。"
            ),
        )
    if len(matches) > 1:
        return ResolvedIndex(
            index=None,
            notice=(
                f"偵測到多個名稱相同的系統音源「{name}」，無法判斷是哪一個，"
                "已改用 Windows 目前的預設輸出。"
            ),
        )
    return ResolvedIndex(index=matches[0].index)
