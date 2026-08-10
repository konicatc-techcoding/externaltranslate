import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CaptionStyleSettings } from "./CaptionStyleSettings";
import { DEFAULT_CAPTION_STYLE, type CaptionStyle } from "../types/runtime";

const STYLE: CaptionStyle = DEFAULT_CAPTION_STYLE;

describe("CaptionStyleSettings", () => {
  it("只列出白名單字型", () => {
    render(<CaptionStyleSettings style={STYLE} onChange={vi.fn()} />);
    const options = Array.from(
      screen.getByLabelText("字型").querySelectorAll("option"),
    ).map((option) => option.textContent);
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

describe("CaptionStyleSettings 的可讀性設定", () => {
  it("可以調描邊粗細與顏色", () => {
    const onChange = vi.fn();
    render(<CaptionStyleSettings style={STYLE} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText("描邊粗細"), {
      target: { value: "4" },
    });
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ outline_width: 4 }),
    );

    fireEvent.change(screen.getByLabelText("描邊顏色"), {
      target: { value: "#101010" },
    });
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ outline_color: "#101010" }),
    );
  });

  it("超出範圍的描邊不送出", () => {
    const onChange = vi.fn();
    render(<CaptionStyleSettings style={STYLE} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText("描邊粗細"), {
      target: { value: "99" },
    });

    expect(onChange).not.toHaveBeenCalled();
  });

  it("背景透明度可以拉到 0，字幕框完全透明", () => {
    const onChange = vi.fn();
    render(<CaptionStyleSettings style={STYLE} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText("背景透明度"), {
      target: { value: "0" },
    });

    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ background_opacity: 0 }),
    );
  });

  it("粗體、陰影與對齊都可切換", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<CaptionStyleSettings style={STYLE} onChange={onChange} />);

    await user.click(screen.getByLabelText("粗體"));
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ weight: "bold" }),
    );

    await user.click(screen.getByLabelText("文字陰影"));
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ shadow: true }),
    );

    await user.selectOptions(screen.getByLabelText("對齊"), "center");
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ align: "center" }),
    );
  });

  it("內距與圓角可以調整", () => {
    const onChange = vi.fn();
    render(<CaptionStyleSettings style={STYLE} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText("內距"), { target: { value: "30" } });
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ padding: 30 }),
    );

    fireEvent.change(screen.getByLabelText("圓角"), { target: { value: "20" } });
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ radius: 20 }),
    );
  });
});
