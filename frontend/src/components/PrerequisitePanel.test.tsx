import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PrerequisitePanel } from "./PrerequisitePanel";
import type { PrerequisiteItem } from "../types/runtime";

function item(overrides: Partial<PrerequisiteItem>): PrerequisiteItem {
  return {
    identifier: "python",
    label: "Python 3.11",
    status: "ready",
    required_for: "v0.1",
    version: "3.11.9",
    detail: "",
    action: "",
    ...overrides,
  };
}

describe("PrerequisitePanel", () => {
  it("如實顯示每個狀態，not_checked 不會被畫成已就緒", () => {
    render(
      <PrerequisitePanel
        items={[
          item({}),
          item({ identifier: "sounddevice", label: "sounddevice", status: "not_checked", version: null }),
          item({ identifier: "ffmpeg", label: "FFmpeg", status: "not_required", version: null }),
        ]}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByText("已就緒")).toBeInTheDocument();
    expect(screen.getByText("尚未檢查")).toBeInTheDocument();
    expect(screen.getByText("本版不需要")).toBeInTheDocument();
    expect(screen.getAllByText("已就緒")).toHaveLength(1);
  });

  it("缺少項目顯示修正建議", () => {
    render(
      <PrerequisitePanel
        items={[item({ status: "missing", action: "請安裝 Python 3.11。" })]}
        onRefresh={vi.fn()}
      />,
    );
    expect(screen.getByText("缺少")).toBeInTheDocument();
    expect(screen.getByText("請安裝 Python 3.11。")).toBeInTheDocument();
  });
});
