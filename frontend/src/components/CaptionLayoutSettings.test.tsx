import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CaptionLayoutSettings } from "./CaptionLayoutSettings";

describe("CaptionLayoutSettings", () => {
  it("顯示目前生效的每行字數與行數", () => {
    render(
      <CaptionLayoutSettings
        layout={{ chars_per_line: 20, max_lines: 2 }}
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
        layout={{ chars_per_line: 20, max_lines: 2 }}
        onChange={onChange}
      />,
    );

    const chars = screen.getByLabelText("每行字數");
    await user.clear(chars);
    await user.type(chars, "10");

    expect(onChange).toHaveBeenLastCalledWith(10, 2);
  });

  it("超出範圍的值不送出，避免打壞現行版面", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <CaptionLayoutSettings
        layout={{ chars_per_line: 20, max_lines: 2 }}
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
        layout={{ chars_per_line: 20, max_lines: 2 }}
        onChange={vi.fn()}
      />,
    );
    rerender(
      <CaptionLayoutSettings
        layout={{ chars_per_line: 6, max_lines: 5 }}
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("每行字數")).toHaveValue(6);
    expect(screen.getByLabelText("行數")).toHaveValue(5);
  });

  it("說明每行字數以全形字計算並可在翻譯中調整", () => {
    render(
      <CaptionLayoutSettings
        layout={{ chars_per_line: 20, max_lines: 2 }}
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
