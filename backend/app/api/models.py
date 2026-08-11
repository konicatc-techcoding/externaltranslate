from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.config import (
    CHARS_PER_LINE_RANGE,
    MAX_LINES_RANGE,
)


class StrictModel(BaseModel):
    """Every request/response model is closed: unknown fields fail closed."""

    model_config = ConfigDict(extra="forbid")


class PrerequisiteItem(StrictModel):
    identifier: str
    label: str
    status: str
    required_for: str
    version: str | None = None
    detail: str = ""
    action: str = ""


class PrerequisiteResponse(StrictModel):
    results: list[PrerequisiteItem]


class DeviceItem(StrictModel):
    index: int
    name: str
    host_api: str
    max_input_channels: int
    default_sample_rate: int


class DeviceResponse(StrictModel):
    devices: list[DeviceItem]


class LoopbackEndpointItem(StrictModel):
    index: int
    name: str
    host_api: str
    channels: int
    default_sample_rate: int
    is_default: bool


class LoopbackEndpointResponse(StrictModel):
    endpoints: list[LoopbackEndpointItem]


class CaptionStyle(StrictModel):
    """Overlay appearance, mirroring `CAPTION_STYLE_FIELDS` in the config.

    Bounds are not repeated here. The runtime validates against that one spec
    table and the route maps the failure to 422, so a field cannot end up
    accepted by the model and rejected by the runtime — or worse, the reverse.
    """

    font: str
    size: int
    weight: str
    color: str
    outline_width: int
    outline_color: str
    shadow: bool
    background_color: str
    background_opacity: float
    padding: int
    radius: int
    align: str
    scroll: bool
    scroll_ms: int


class VmixSettings(StrictModel):
    """vMix output settings. `enabled` mirrors `features.vmix_output`."""

    enabled: bool
    host: str
    port: int
    input_guid: str | None
    input_name: str | None
    fields: list[str]
    min_interval_ms: int
    timeout_ms: int


class VmixSettingsUpdate(StrictModel):
    """Every field optional: the panel changes one thing at a time."""

    enabled: bool | None = None
    host: str | None = None
    port: int | None = None
    input_guid: str | None = None
    input_name: str | None = None
    fields: list[str] | None = None
    min_interval_ms: int | None = None
    timeout_ms: int | None = None


class VmixInputItem(StrictModel):
    guid: str
    number: int
    name: str
    kind: str
    #: Names the operator must give the title's text fields.
    text_fields: list[str]


class VmixInputList(StrictModel):
    inputs: list[VmixInputItem]


class VmixTestRequest(StrictModel):
    """Lines to write. Omitted means "one marker per configured field"."""

    lines: list[str] | None = Field(default=None, max_length=10)


class VmixTestResponse(StrictModel):
    message: str
    #: Exactly what was written, so the operator can compare with the screen.
    lines: list[str]


class UiSettings(StrictModel):
    """Which control-page panels are folded away."""

    collapsed: list[str]


class SettingsResponse(StrictModel):
    source_kind: str
    device_index: int | None
    loopback_endpoint_index: int | None
    channel: int
    caption_max_payload_length: int
    caption_chars_per_line: int
    caption_max_lines: int
    caption_sentence_breaks: bool
    caption_style: CaptionStyle
    vmix: VmixSettings
    ui: UiSettings
    session_rotation_seconds: int


class CaptionLayoutUpdate(StrictModel):
    """Display layout, adjustable while translating."""

    chars_per_line: int = Field(ge=CHARS_PER_LINE_RANGE[0], le=CHARS_PER_LINE_RANGE[1])
    max_lines: int = Field(ge=MAX_LINES_RANGE[0], le=MAX_LINES_RANGE[1])
    sentence_breaks: bool = True


class CaptionStyleUpdate(CaptionStyle):
    """Overlay appearance, adjustable while translating."""


class SettingsUpdate(StrictModel):
    source_kind: Literal["input_device", "wasapi_loopback"]
    device_index: int | None = Field(default=None, ge=0)
    loopback_endpoint_index: int | None = Field(default=None, ge=0)
    channel: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _enforce_source_exclusivity(self) -> SettingsUpdate:
        # INPUT_DEVICE XOR WASAPI_LOOPBACK, validated before it reaches runtime.
        if self.source_kind == "input_device":
            if self.device_index is None:
                raise ValueError("選擇輸入裝置時必須提供 device_index。")
            if self.loopback_endpoint_index is not None:
                raise ValueError("輸入裝置模式不得同時指定 loopback_endpoint_index。")
        else:
            if self.device_index is not None:
                raise ValueError("系統輸出模式不得同時指定 device_index。")
        return self


class CredentialSubmit(StrictModel):
    api_key: str = Field(min_length=1)


class CredentialState(StrictModel):
    """Deliberately carries no fragment of the key — not even a masked tail."""

    configured: bool


class CredentialTestResult(StrictModel):
    result: Literal["ok", "auth_failed", "network_error", "not_configured"]
    message: str


class ComponentStatusItem(StrictModel):
    component: str
    state: str
    detail: str | None
    revision: int
    session_generation: int | None
    updated_at: float


class CaptionPayload(StrictModel):
    revision: int
    status: str
    text: str
    #: Wrapped display window; every consumer renders these same lines.
    lines: list[str]
    language_code: str
    updated_at: float
    session_generation: int


class MeterPayload(StrictModel):
    rms: float
    peak: float
    rms_dbfs: float
    peak_dbfs: float
    clipping: bool


class CaptionLayout(StrictModel):
    chars_per_line: int
    max_lines: int
    #: A sentence ending near the line edge starts the next one on a new line.
    sentence_breaks: bool = True


class RuntimeStatusResponse(StrictModel):
    running: bool
    #: Sent with every snapshot so an overlay can size its box without a
    #: second request.
    layout: CaptionLayout
    style: CaptionStyle
    elapsed_seconds: float
    status_revision: int
    components: list[ComponentStatusItem]
    caption: CaptionPayload
    meter: MeterPayload | None
    last_error: str | None
    #: Why the audio source saved last time could not be restored, if it
    #: could not. Silently falling back to no selection would read as the
    #: setting having been forgotten.
    audio_notice: str | None = None
    #: Why vMix output is not running although it was switched on. Separate
    #: from `last_error`: translation itself is fine.
    vmix_notice: str | None = None


class CaptionPresetItem(CaptionStyle):
    name: str
    chars_per_line: int
    max_lines: int
    sentence_breaks: bool = True


class CaptionPresetList(StrictModel):
    presets: list[CaptionPresetItem]


class CaptionPresetSave(StrictModel):
    name: str = Field(min_length=1, max_length=60)


class MessageResponse(StrictModel):
    message: str


def as_dict(model: BaseModel) -> dict[str, Any]:
    return model.model_dump()
