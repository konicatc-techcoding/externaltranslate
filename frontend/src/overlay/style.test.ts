import { describe, expect, it } from "vitest";

import {
  DEFAULT_OVERLAY_STYLE,
  FONT_STACKS,
  hexToRgba,
  parseOverlayStyle,
  toCssVariables,
} from "./style";

function parse(query: string) {
  return parseOverlayStyle(new URLSearchParams(query));
}

describe("overlay style parameters", () => {
  it("沒有參數時使用預設值", () => {
    expect(parse("")).toEqual(DEFAULT_OVERLAY_STYLE);
  });

  it("套用合法參數", () => {
    expect(parse("width=1600&lines=3&size=64&font=serif&color=%23FF0000&bg=%23112233&opacity=0.25&align=center")).toEqual({
      width: "1600px",
      lines: 3,
      size: 64,
      font: FONT_STACKS.serif,
      color: "#FF0000",
      bg: "#112233",
      opacity: 0.25,
      align: "center",
    });
  });

  it("預設由左至右，字幕不會隨長度左右飄移", () => {
    expect(parse("").align).toBe("left");
    expect(parse("align=center").align).toBe("center");
    expect(parse("align=right").align).toBe("right");
  });

  it("接受百分比寬度", () => {
    expect(parse("width=75%").width).toBe("75%");
  });

  it("非法顏色一律回預設，不得注入 CSS", () => {
    expect(parse("color=red").color).toBe(DEFAULT_OVERLAY_STYLE.color);
    expect(parse("bg=%23fff;background:url(x)").bg).toBe(DEFAULT_OVERLAY_STYLE.bg);
    expect(parse("color=%23GGGGGG").color).toBe(DEFAULT_OVERLAY_STYLE.color);
  });

  it("字型只接受白名單", () => {
    expect(parse("font=serif").font).toBe(FONT_STACKS.serif);
    expect(parse("font=Comic Sans, url(evil)").font).toBe(DEFAULT_OVERLAY_STYLE.font);
  });

  it("超出範圍的數值回預設", () => {
    expect(parse("lines=0").lines).toBe(DEFAULT_OVERLAY_STYLE.lines);
    expect(parse("lines=99").lines).toBe(DEFAULT_OVERLAY_STYLE.lines);
    expect(parse("size=4").size).toBe(DEFAULT_OVERLAY_STYLE.size);
    expect(parse("size=1000").size).toBe(DEFAULT_OVERLAY_STYLE.size);
    expect(parse("opacity=5").opacity).toBe(DEFAULT_OVERLAY_STYLE.opacity);
    expect(parse("opacity=-1").opacity).toBe(DEFAULT_OVERLAY_STYLE.opacity);
    expect(parse("align=diagonal").align).toBe(DEFAULT_OVERLAY_STYLE.align);
  });

  it("opacity 0 代表完全透明", () => {
    expect(parse("opacity=0").opacity).toBe(0);
    expect(hexToRgba("#000000", 0)).toBe("rgba(0, 0, 0, 0)");
  });

  it("行數換算成字幕框高度", () => {
    const variables = toCssVariables(parse("lines=3&size=50")) as Record<string, string>;
    expect(variables["--caption-height"]).toBe("195.00px");
    expect(variables["--caption-line-height"]).toBe("1.3");
  });
});
