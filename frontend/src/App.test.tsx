import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { IDLE_RUNTIME_STATUS } from "./types/runtime";

class SilentSocket {
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  close(): void {}
}

const RESPONSES: Record<string, unknown> = {
  "/api/prerequisites": {
    results: [
      {
        identifier: "python",
        label: "Python 3.11",
        status: "ready",
        required_for: "v0.1",
        version: "3.11.9",
        detail: "",
        action: "",
      },
    ],
  },
  "/api/devices": { devices: [] },
  "/api/loopback-endpoints": { endpoints: [] },
  "/api/settings": {
    source_kind: "wasapi_loopback",
    device_index: null,
    loopback_endpoint_index: null,
    channel: 1,
    caption_max_payload_length: 4096,
    caption_chars_per_line: 20,
    caption_max_lines: 2,
    session_rotation_seconds: 480,
  },
  "/api/credentials": { configured: false },
  "/api/pipeline/status": IDLE_RUNTIME_STATUS,
};

beforeEach(() => {
  vi.stubGlobal("WebSocket", SilentSocket);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) => ({
      ok: true,
      status: 200,
      json: async () => RESPONSES[path] ?? {},
    })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("App", () => {
  it("預設路徑顯示繁體中文控制台", async () => {
    render(<App pathname="/" />);

    expect(
      screen.getByRole("heading", { name: "ExternalTranslate" }),
    ).toBeInTheDocument();
    expect(screen.getByText("即時翻譯字幕控制台")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText("環境檢查")).toBeInTheDocument(),
    );
  });

  it("/overlay 只顯示字幕，沒有任何控制項", () => {
    const { container } = render(<App pathname="/overlay" />);

    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByLabelText("API Key 輸入欄")).toBeNull();
    expect(container.querySelector(".overlay-shell")).not.toBeNull();
  });

  it("/overlay/ 尾斜線同樣視為 overlay", () => {
    const { container } = render(<App pathname="/overlay/" />);
    expect(container.querySelector(".overlay-shell")).not.toBeNull();
  });
});
