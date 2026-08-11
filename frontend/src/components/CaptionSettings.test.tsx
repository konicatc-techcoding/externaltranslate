import { describe, expect, it } from "vitest";

import { captionSummary } from "./CaptionSettings";
import { DEFAULT_CAPTION_STYLE } from "../types/runtime";

const LAYOUT = {
  chars_per_line: 20,
  max_lines: 5,
  sentence_breaks: true,
  idle_reset_ms: 0,
};

describe("captionSummary", () => {
  it("答得出折疊面板裡是什麼設定", () => {
    expect(captionSummary(LAYOUT, DEFAULT_CAPTION_STYLE)).toBe(
      "20 字 5 行・微軟正黑體 48px",
    );
  });

  it("開著停頓重來時要講出來，那是唯一會自己丟掉字幕的設定", () => {
    expect(
      captionSummary({ ...LAYOUT, idle_reset_ms: 2500 }, DEFAULT_CAPTION_STYLE),
    ).toBe("20 字 5 行・停頓 2.5 秒重來・微軟正黑體 48px");
  });
});
