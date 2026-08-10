import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CaptionStyleSettings } from "./CaptionStyleSettings";
import type { CaptionStyle } from "../types/runtime";

const STYLE: CaptionStyle = {
  font: "jhenghei",
  size: 48,
  scroll: true,
  scroll_ms: 250,
  color: "#FFFFFF",
};

describe("CaptionStyleSettings", () => {
  it("只列出白名單字型", () => {
    render(<CaptionStyleSettings style={STYLE} onChange={vi.fn()} />);
    const options = screen
      .getAllByRole("option")
      .map((option) => option.textContent);
    expect(options).toEqual([
      "微軟正黑體",
      "標楷體",
      "Noto Sans TC（需另行安裝）",
    ]);
  });

  it("切換字型時送出完整樣式", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<CaptionStyleSettings style={STYLE} onChange={onChange} />);

    await user.selectOptions(screen.getByLabelText("字型"), "kai");

    expect(onChange).toHaveBeenCalledWith({ ...STYLE, font: "kai" });
  });

  it("選到需安裝的字型時提醒播放端可能沒有", () => {
    const { rerender } = render(
      <CaptionStyleSettings style={STYLE} onChange={vi.fn()} />,
    );
    expect(
      screen.queryByText(
        "此字型需在播放端另行安裝，未安裝會自動改用其他字型。",
      ),
    ).toBeNull();

    rerender(
      <CaptionStyleSettings
        style={{ ...STYLE, font: "noto-sans-tc" }}
        onChange={vi.fn()}
      />,
    );
    expect(
      screen.getByText("此字型需在播放端另行安裝，未安裝會自動改用其他字型。"),
    ).toBeInTheDocument();
  });

  it("超出範圍的字級不送出", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<CaptionStyleSettings style={STYLE} onChange={onChange} />);

    const size = screen.getByLabelText("字級");
    await user.clear(size);
    await user.type(size, "999");

    expect(onChange).not.toHaveBeenCalledWith(
      expect.objectContaining({ size: 999 }),
    );
  });

  it("關閉滑動時停用滑動時間", () => {
    render(
      <CaptionStyleSettings
        style={{ ...STYLE, scroll: false }}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("滑動時間（毫秒）")).toBeDisabled();
  });

  it("切換滑動開關", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<CaptionStyleSettings style={STYLE} onChange={onChange} />);

    await user.click(screen.getByLabelText("向上滑動效果"));

    expect(onChange).toHaveBeenCalledWith({ ...STYLE, scroll: false });
  });

  it("可以改文字顏色", () => {
    const onChange = vi.fn();
    render(<CaptionStyleSettings style={STYLE} onChange={onChange} />);

    const color = screen.getByLabelText("文字顏色");
    expect(color).toHaveAttribute("type", "color");
    // a colour input is not typed into; the picker fires a change event
    fireEvent.change(color, { target: { value: "#ffcc00" } });

    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ color: "#FFCC00" }),
    );
  });

  it("說明只影響網頁 overlay", () => {
    render(<CaptionStyleSettings style={STYLE} onChange={vi.fn()} />);
    expect(
      screen.getByText(
        "只影響網頁 overlay；vMix GT Title 有自己的字型與動畫設定。",
      ),
    ).toBeInTheDocument();
  });
});
