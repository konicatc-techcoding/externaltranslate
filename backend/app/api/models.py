from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class SettingsResponse(StrictModel):
    source_kind: str
    device_index: int | None
    loopback_endpoint_index: int | None
    channel: int
    caption_max_payload_length: int
    session_rotation_seconds: int


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
    language_code: str
    updated_at: float
    session_generation: int


class MeterPayload(StrictModel):
    rms: float
    peak: float
    rms_dbfs: float
    peak_dbfs: float
    clipping: bool


class RuntimeStatusResponse(StrictModel):
    running: bool
    status_revision: int
    components: list[ComponentStatusItem]
    caption: CaptionPayload
    meter: MeterPayload | None
    last_error: str | None


class MessageResponse(StrictModel):
    message: str


def as_dict(model: BaseModel) -> dict[str, Any]:
    return model.model_dump()
