export type ComponentName =
  | "audio_source"
  | "gemini_provider"
  | "gemini_session"
  | "caption_sink";

export interface ComponentStatus {
  component: ComponentName;
  state: string;
  detail: string | null;
  revision: number;
  session_generation: number | null;
  updated_at: number;
}

export type CaptionStatus = "idle" | "partial" | "final";

export interface CaptionPayload {
  revision: number;
  status: CaptionStatus;
  text: string;
  language_code: string;
  updated_at: number;
  session_generation: number;
}

export interface MeterPayload {
  rms: number;
  peak: number;
  rms_dbfs: number;
  peak_dbfs: number;
  clipping: boolean;
}

export interface RuntimeStatus {
  running: boolean;
  /** Duration of the current (or last) translation run, in seconds. */
  elapsed_seconds: number;
  status_revision: number;
  components: ComponentStatus[];
  caption: CaptionPayload;
  meter: MeterPayload | null;
  last_error: string | null;
}

export interface PrerequisiteItem {
  identifier: string;
  label: string;
  status: "ready" | "missing" | "not_required" | "optional" | "not_checked";
  required_for: string;
  version: string | null;
  detail: string;
  action: string;
}

export interface DeviceItem {
  index: number;
  name: string;
  host_api: string;
  max_input_channels: number;
  default_sample_rate: number;
}

export interface LoopbackEndpointItem {
  index: number;
  name: string;
  host_api: string;
  channels: number;
  default_sample_rate: number;
  is_default: boolean;
}

export type SourceKind = "input_device" | "wasapi_loopback";

export interface AppSettings {
  source_kind: SourceKind;
  device_index: number | null;
  loopback_endpoint_index: number | null;
  channel: number;
  caption_max_payload_length: number;
  session_rotation_seconds: number;
}

export interface CredentialState {
  configured: boolean;
}

export interface CredentialTestResult {
  result: "ok" | "auth_failed" | "network_error" | "not_configured";
  message: string;
}

export const IDLE_RUNTIME_STATUS: RuntimeStatus = {
  running: false,
  elapsed_seconds: 0,
  status_revision: 0,
  components: [],
  caption: {
    revision: 0,
    status: "idle",
    text: "",
    language_code: "",
    updated_at: 0,
    session_generation: 0,
  },
  meter: null,
  last_error: null,
};
