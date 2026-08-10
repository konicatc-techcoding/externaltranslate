from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from backend.app.config import (
    CAPTION_STYLE_FIELDS,
    CHARS_PER_LINE_RANGE,
    MAX_LINES_RANGE,
)

MAX_NAME_LENGTH = 60
MAX_PRESETS = 50


class PresetError(ValueError):
    """Raised when a caption preset is invalid or missing."""


@dataclass(frozen=True)
class CaptionPreset:
    """A named caption layout plus appearance, safe to write to disk.

    Only non-secret display settings live here; nothing in this shape can
    carry a credential.

    Every appearance field has a default so a preset saved before that field
    existed still loads. Without this, adding a field would make the operator's
    saved presets fail to construct and silently disappear from the list.
    """

    name: str
    chars_per_line: int
    max_lines: int
    font: str
    size: int
    color: str
    scroll: bool
    scroll_ms: int
    sentence_breaks: bool = True
    weight: str = "normal"
    outline_width: int = 0
    outline_color: str = "#000000"
    shadow: bool = False
    background_color: str = "#000000"
    background_opacity: float = 0.5
    padding: int = 12
    radius: int = 8
    align: str = "left"


def _validate(preset: CaptionPreset) -> None:
    name = preset.name.strip()
    if not name:
        raise PresetError("預設名稱不得空白。")
    if len(name) > MAX_NAME_LENGTH:
        raise PresetError(f"預設名稱不得超過 {MAX_NAME_LENGTH} 個字元。")
    if not _in_range(preset.chars_per_line, CHARS_PER_LINE_RANGE):
        raise PresetError("每行字數超出允許範圍。")
    if not _in_range(preset.max_lines, MAX_LINES_RANGE):
        raise PresetError("行數超出允許範圍。")
    if not isinstance(preset.sentence_breaks, bool):
        raise PresetError("句尾換行設定必須是 boolean。")
    # Appearance is checked against the same spec the settings API uses, so a
    # preset can never carry a value the runtime would refuse to apply.
    for field in CAPTION_STYLE_FIELDS:
        value = getattr(preset, field.name)
        if not field.check(value):
            raise PresetError(field.error.replace("caption.", "字幕設定 "))


def _in_range(value: Any, bounds: tuple[int, int]) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and bounds[0] <= value <= bounds[1]
    )


class PresetStore:
    """Named caption presets in one JSON file.

    Presets are keyed by name *inside* the file rather than stored as separate
    files, so a name can never be interpreted as a filesystem path. A file
    that is corrupt or partly invalid degrades to whatever still parses: a bad
    preset must not stop the operator from running a show.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def list(self) -> list[CaptionPreset]:
        return sorted(self._read().values(), key=lambda preset: preset.name)

    def get(self, name: str) -> CaptionPreset:
        presets = self._read()
        if name not in presets:
            raise PresetError(f"找不到名為「{name}」的字幕預設。")
        return presets[name]

    def save(self, preset: CaptionPreset) -> None:
        _validate(preset)
        presets = self._read()
        if preset.name not in presets and len(presets) >= MAX_PRESETS:
            raise PresetError(f"預設數量已達上限 {MAX_PRESETS} 組。")
        presets[preset.name] = preset
        self._write(presets)

    def delete(self, name: str) -> None:
        presets = self._read()
        if name not in presets:
            raise PresetError(f"找不到名為「{name}」的字幕預設。")
        del presets[name]
        self._write(presets)

    # ------------------------------------------------------------------ io

    def _read(self) -> dict[str, CaptionPreset]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, dict):
            return {}

        presets: dict[str, CaptionPreset] = {}
        for entry in raw.values():
            if not isinstance(entry, dict):
                continue
            try:
                preset = CaptionPreset(**entry)
                _validate(preset)
            except (TypeError, PresetError):
                continue  # skip the broken entry, keep the usable ones
            presets[preset.name] = preset
        return presets

    def _write(self, presets: dict[str, CaptionPreset]) -> None:
        payload = {name: asdict(preset) for name, preset in presets.items()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Write via a temporary file so an interrupted save cannot leave a
        # half-written file that reads as "no presets".
        temporary = self.path.with_suffix(".tmp")
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temporary.replace(self.path)
        except OSError as exc:
            raise PresetError(f"無法寫入字幕預設檔：{exc}") from None
