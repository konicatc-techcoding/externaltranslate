import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ManualCaptions } from "./ManualCaptions";

const SLOTS = ["請稍候", "節目稍後開始", "", "", ""];

function renderPanel(overrides: Partial<Parameters<typeof ManualCaptions>[0]> = {}) {
  const props = {
    slots: SLOTS,
    charsPerLine: 20,
    onSlotsChange: vi.fn(),
    onCharsPerLineChange: vi.fn(),
    onSend: vi.fn(),
    onClear: vi.fn(),
    ...overrides,
  };
  render(<ManualCaptions {...props} />);
  return props;
}

describe("ManualCaptions", () => {
  it("送出目前選中的那一格", async () => {
    const user = userEvent.setup();
    const props = renderPanel();

    await user.click(screen.getByRole("button", { name: "發送 ON AIR" }));

    expect(props.onSend).toHaveBeenCalledWith("請稍候");
  });

  it("改選第二格再送出，送的是第二格", async () => {
    const user = userEvent.setup();
    const props = renderPanel();

    await user.click(screen.getAllByRole("radio")[1]);
    await user.click(screen.getByRole("button", { name: "發送 ON AIR" }));

    expect(props.onSend).toHaveBeenCalledWith("節目稍後開始");
  });

  it("改了內容再送出，送的是改過的文字", async () => {
    // The operator's actual flow: pick a box, retype it, hit send.
    const user = userEvent.setup();
    const props = renderPanel();

    const second = screen.getByLabelText("字幕 2");
    await user.clear(second);
    await user.type(second, "十分鐘後開始");
    await user.click(screen.getByRole("button", { name: "發送 ON AIR" }));

    expect(props.onSend).toHaveBeenCalledWith("十分鐘後開始");
  });

  it("送出時一併存下來，不必另外按儲存", async () => {
    const user = userEvent.setup();
    const props = renderPanel();

    const first = screen.getByLabelText("字幕 1");
    await user.clear(first);
    await user.type(first, "馬上回來");
    await user.click(screen.getByRole("button", { name: "發送 ON AIR" }));

    expect(props.onSlotsChange).toHaveBeenLastCalledWith([
      "馬上回來",
      "節目稍後開始",
      "",
      "",
      "",
    ]);
  });

  it("空白的格子不能送出", async () => {
    const user = userEvent.setup();
    renderPanel({ slots: ["", "", "", "", ""] });

    expect(screen.getByRole("button", { name: "發送 ON AIR" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "清空" }));
  });

  it("顯示目前在畫面上的是哪一句", () => {
    renderPanel({ lastSent: ["請稍候"] });

    expect(screen.getByText("ON AIR")).toBeInTheDocument();
    expect(screen.getByText("請稍候")).toBeInTheDocument();
  });

  it("超出欄位數時要說出來", () => {
    renderPanel({ lastSent: ["太長了"], overflowed: true });

    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});

describe("每行字數", () => {
  it("是手動字幕自己的，不跟著即時翻譯", async () => {
    const user = userEvent.setup();
    const props = renderPanel({ charsPerLine: 20 });

    const width = screen.getByLabelText("每行字數");
    expect(width).toHaveValue(20);

    await user.clear(width);
    await user.type(width, "30");

    expect(props.onCharsPerLineChange).toHaveBeenLastCalledWith(30);
  });

  it("超出範圍的值不送出", async () => {
    const user = userEvent.setup();
    const props = renderPanel({ charsPerLine: 20 });

    const width = screen.getByLabelText("每行字數");
    await user.clear(width);
    await user.type(width, "99");

    expect(props.onCharsPerLineChange).not.toHaveBeenCalledWith(99);
  });
});
