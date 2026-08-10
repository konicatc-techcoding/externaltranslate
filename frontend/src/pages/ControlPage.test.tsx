import { describe, expect, it } from "vitest";

import { deriveUiState } from "./ControlPage";
import { IDLE_RUNTIME_STATUS, type RuntimeStatus } from "../types/runtime";

function status(overrides: Partial<RuntimeStatus> = {}): RuntimeStatus {
  return { ...IDLE_RUNTIME_STATUS, ...overrides };
}

describe("控制頁狀態機", () => {
  const base = {
    loading: false,
    stopping: false,
    error: null as string | null,
    configured: true,
    status: status(),
  };

  it("尚未設定 key 時為待命", () => {
    expect(deriveUiState({ ...base, configured: false })).toBe("idle");
  });

  it("載入中為檢查環境", () => {
    expect(deriveUiState({ ...base, loading: true })).toBe("checking");
  });

  it("設定完成但未開始為可以開始", () => {
    expect(deriveUiState(base)).toBe("ready");
  });

  it("執行中但尚無字幕為聆聽中", () => {
    expect(deriveUiState({ ...base, status: status({ running: true }) })).toBe(
      "listening",
    );
  });

  it("收到字幕後為翻譯中", () => {
    const running = status({
      running: true,
      caption: { ...IDLE_RUNTIME_STATUS.caption, status: "partial", text: "你好" },
    });
    expect(deriveUiState({ ...base, status: running })).toBe("translating");
  });

  it("停止中優先於執行狀態", () => {
    expect(
      deriveUiState({ ...base, stopping: true, status: status({ running: true }) }),
    ).toBe("stopping");
  });

  it("錯誤優先於一切", () => {
    expect(
      deriveUiState({
        ...base,
        error: "無法連線",
        stopping: true,
        status: status({ running: true }),
      }),
    ).toBe("error");
  });
});
