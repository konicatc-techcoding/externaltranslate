import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CaptionPresets } from "./CaptionPresets";
import type { CaptionPreset } from "../types/runtime";

const PRESET: CaptionPreset = {
  name: "記者會",
  chars_per_line: 10,
  max_lines: 3,
  font: "kai",
  size: 72,
  color: "#FFCC00",
  scroll: false,
  scroll_ms: 400,
};

function renderPresets(presets: CaptionPreset[] = [], handlers = {}) {
  const props = {
    presets,
    onSave: vi.fn(),
    onApply: vi.fn(),
    onDelete: vi.fn(),
    ...handlers,
  };
  render(<CaptionPresets {...props} />);
  return props;
}

describe("CaptionPresets", () => {
  it("沒有預設時說明尚未儲存", () => {
    renderPresets();
    expect(screen.getByText("尚未儲存任何預設。")).toBeInTheDocument();
  });

  it("以名稱儲存目前設定", async () => {
    const user = userEvent.setup();
    const props = renderPresets();

    await user.type(screen.getByLabelText("預設名稱"), "記者會");
    await user.click(screen.getByRole("button", { name: "儲存目前設定" }));

    expect(props.onSave).toHaveBeenCalledWith("記者會");
    expect(screen.getByLabelText("預設名稱")).toHaveValue("");
  });

  it("空白名稱不能儲存", async () => {
    const user = userEvent.setup();
    const props = renderPresets();

    expect(screen.getByRole("button", { name: "儲存目前設定" })).toBeDisabled();
    await user.type(screen.getByLabelText("預設名稱"), "   ");
    await user.click(screen.getByRole("button", { name: "儲存目前設定" }));
    expect(props.onSave).not.toHaveBeenCalled();
  });

  it("列出預設的內容摘要", () => {
    renderPresets([PRESET]);
    expect(screen.getByText("記者會")).toBeInTheDocument();
    expect(
      screen.getByText("10字 × 3行 · 72px · #FFCC00"),
    ).toBeInTheDocument();
  });

  it("套用與刪除", async () => {
    const user = userEvent.setup();
    const props = renderPresets([PRESET]);

    await user.click(screen.getByRole("button", { name: "套用" }));
    expect(props.onApply).toHaveBeenCalledWith("記者會");

    await user.click(screen.getByRole("button", { name: "刪除" }));
    expect(props.onDelete).toHaveBeenCalledWith("記者會");
  });

  it("刪除是破壞性操作，以紅色標示", () => {
    renderPresets([PRESET]);
    expect(screen.getByRole("button", { name: "刪除" }).className).toContain(
      "button--danger",
    );
  });
});
