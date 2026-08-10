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
  /** Wrapped display window produced by the backend formatter. */
  lines: string[];
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

export interface CaptionLayout {
  chars_per_line: number;
  max_lines: number;
  /** A sentence ending near the line edge starts the next one on a new line. */
  sentence_breaks: boolean;
}

export interface CaptionStyle {
  font: string;
  size: number;
  weight: string;
  color: string;
  outline_width: number;
  outline_color: string;
  shadow: boolean;
  background_color: string;
  background_opacity: number;
  padding: number;
  radius: number;
  align: string;
  scroll: boolean;
  scroll_ms: number;
}

export const DEFAULT_CAPTION_STYLE: CaptionStyle = {
  font: "jhenghei",
  size: 48,
  weight: "normal",
  color: "#FFFFFF",
  outline_width: 0,
  outline_color: "#000000",
  shadow: false,
  background_color: "#000000",
  background_opacity: 0.5,
  padding: 12,
  radius: 8,
  align: "left",
  scroll: true,
  scroll_ms: 250,
};

export interface RuntimeStatus {
  running: boolean;
  layout: CaptionLayout;
  style: CaptionStyle;
  /** Duration of the current (or last) translation run, in seconds. */
  elapsed_seconds: number;
  status_revision: number;
  components: ComponentStatus[];
  caption: CaptionPayload;
  meter: MeterPayload | null;
  last_error: string | null;
  /** Why the audio source saved last time could not be restored, if it could not. */
  audio_notice: string | null;
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
  caption_chars_per_line: number;
  caption_max_lines: number;
  caption_sentence_breaks: boolean;
  caption_style: CaptionStyle;
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
  layout: { chars_per_line: 20, max_lines: 2, sentence_breaks: true },
  style: DEFAULT_CAPTION_STYLE,
  elapsed_seconds: 0,
  status_revision: 0,
  components: [],
  caption: {
    revision: 0,
    status: "idle",
    text: "",
    lines: [],
    language_code: "",
    updated_at: 0,
    session_generation: 0,
  },
  meter: null,
  last_error: null,
  audio_notice: null,
};

export interface CaptionPreset extends CaptionStyle {
  name: string;
  chars_per_line: number;
  max_lines: number;
  sentence_breaks: boolean;
}
