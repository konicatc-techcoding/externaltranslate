import type {
  AppSettings,
  CredentialState,
  CredentialTestResult,
  DeviceItem,
  LoopbackEndpointItem,
  PrerequisiteItem,
  RuntimeStatus,
  SourceKind,
} from "../types/runtime";

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const GENERIC_ERROR = "無法連線本機服務，請確認服務是否啟動。";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(GENERIC_ERROR, 0);
  }
  if (!response.ok) {
    throw new ApiError(await readErrorMessage(response), response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

async function readErrorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    const detail = body.detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
    // FastAPI validation errors arrive as a list; keep them out of the UI.
    if (Array.isArray(detail)) {
      return "送出的設定不符合格式，請確認後再試。";
    }
  } catch {
    // fall through to the generic message
  }
  return GENERIC_ERROR;
}

export const api = {
  prerequisites: () =>
    request<{ results: PrerequisiteItem[] }>("/api/prerequisites"),

  devices: () => request<{ devices: DeviceItem[] }>("/api/devices"),

  loopbackEndpoints: () =>
    request<{ endpoints: LoopbackEndpointItem[] }>("/api/loopback-endpoints"),

  settings: () => request<AppSettings>("/api/settings"),

  updateSettings: (update: {
    source_kind: SourceKind;
    device_index?: number | null;
    loopback_endpoint_index?: number | null;
    channel?: number | null;
  }) =>
    request<AppSettings>("/api/settings", {
      method: "PUT",
      body: JSON.stringify(update),
    }),

  credentialState: () => request<CredentialState>("/api/credentials"),

  /**
   * The key is passed straight to the local service and never kept here:
   * no module-level variable, no storage, no URL parameter.
   */
  submitCredential: (apiKey: string) =>
    request<CredentialState>("/api/credentials", {
      method: "PUT",
      body: JSON.stringify({ api_key: apiKey }),
    }),

  clearCredential: () =>
    request<CredentialState>("/api/credentials", { method: "DELETE" }),

  testCredential: () =>
    request<CredentialTestResult>("/api/credentials/test", { method: "POST" }),

  start: () => request<{ message: string }>("/api/pipeline/start", { method: "POST" }),

  stop: () => request<{ message: string }>("/api/pipeline/stop", { method: "POST" }),

  status: () => request<RuntimeStatus>("/api/pipeline/status"),
};
