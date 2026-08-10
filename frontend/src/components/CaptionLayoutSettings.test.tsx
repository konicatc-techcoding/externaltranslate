import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CaptionLayoutSettings } from "./CaptionLayoutSettings";

describe("CaptionLayoutSettings", () => {
  it("顯示目前生效的每行字數與行數", () => {
    render(
      <CaptionLayoutSettings
        layout={{ chars_per_line: 20, max_lines: 2, sentence_breaks: true }}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("每行字數")).toHaveValue(20);
    expect(screen.getByLabelText("行數")).toHaveValue(2);
  });

  it("調整後送出新的版面", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <CaptionLayoutSettings
        layout={{ chars_per_line: 20, max_lines: 2, sentence_breaks: true }}
        onChange={onChange}
      />,
    );

    const chars = screen.getByLabelText("每行字數");
    await user.clear(chars);
    await user.type(chars, "10");

    expect(onChange).toHaveBeenLastCalledWith({
      chars_per_line: 10,
      max_lines: 2,
      sentence_breaks: true,
    });
  });

  it("超出範圍的值不送出，避免打壞現行版面", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <CaptionLayoutSettings
        layout={{ chars_per_line: 20, max_lines: 2, sentence_breaks: true }}
        onChange={onChange}
      />,
    );

    const lines = screen.getByLabelText("行數");
    await user.clear(lines);
    await user.type(lines, "99");

    expect(onChange).not.toHaveBeenCalledWith(20, 99);
  });

  it("以伺服器回報的值為準", () => {
    const { rerender } = render(
      <CaptionLayoutSettings
        layout={{ chars_per_line: 20, max_lines: 2, sentence_breaks: true }}
        onChange={vi.fn()}
      />,
    );
    rerender(
      <CaptionLayoutSettings
        layout={{ chars_per_line: 6, max_lines: 5, sentence_breaks: true }}
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("每行字數")).toHaveValue(6);
    expect(screen.getByLabelText("行數")).toHaveValue(5);
  });

  it("說明每行字數以全形字計算並可在翻譯中調整", () => {
    render(
      <CaptionLayoutSettings
        layout={{ chars_per_line: 20, max_lines: 2, sentence_breaks: true }}
        onChange={vi.fn()}
      />,
    );
    expect(
      screen.getByText(
        "每行字數以全形字計算；翻譯進行中也可以調整，會立即重新排版。",
      ),
    ).toBeInTheDocument();
  });
});

describe("句尾換行", () => {
  it("可以關閉，其餘版面設定不變", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <CaptionLayoutSettings
        layout={{ chars_per_line: 20, max_lines: 2, sentence_breaks: true }}
        onChange={onChange}
      />,
    );

    await user.click(screen.getByLabelText("句尾換行"));

    expect(onChange).toHaveBeenLastCalledWith({
      chars_per_line: 20,
      max_lines: 2,
      sentence_breaks: false,
    });
  });

  it("說明門檻是剩餘空間而不是比例", () => {
    render(
      <CaptionLayoutSettings
        layout={{ chars_per_line: 20, max_lines: 2, sentence_breaks: true }}
        onChange={vi.fn()}
      />,
    );
    expect(
      screen.getByText(/剩下不足 4 個全形字/),
    ).toBeInTheDocument();
  });
});
