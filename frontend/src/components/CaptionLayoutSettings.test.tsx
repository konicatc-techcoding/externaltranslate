import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CaptionLayoutSettings } from "./CaptionLayoutSettings";

describe("CaptionLayoutSettings", () => {
  it("顯示目前生效的每行字數與行數", () => {
    render(
      <CaptionLayoutSettings
        layout={{ chars_per_line: 20, max_lines: 2, sentence_breaks: true, idle_reset_ms: 0 }}
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
        layout={{ chars_per_line: 20, max_lines: 2, sentence_breaks: true, idle_reset_ms: 0 }}
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
      idle_reset_ms: 0,
    });
  });

  it("超出範圍的值不送出，避免打壞現行版面", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <CaptionLayoutSettings
        layout={{ chars_per_line: 20, max_lines: 2, sentence_breaks: true, idle_reset_ms: 0 }}
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
        layout={{ chars_per_line: 20, max_lines: 2, sentence_breaks: true, idle_reset_ms: 0 }}
        onChange={vi.fn()}
      />,
    );
    rerender(
      <CaptionLayoutSettings
        layout={{ chars_per_line: 6, max_lines: 5, sentence_breaks: true, idle_reset_ms: 0 }}
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("每行字數")).toHaveValue(6);
    expect(screen.getByLabelText("行數")).toHaveValue(5);
  });

  it("說明每行字數以全形字計算並可在翻譯中調整", () => {
    render(
      <CaptionLayoutSettings
        layout={{ chars_per_line: 20, max_lines: 2, sentence_breaks: true, idle_reset_ms: 0 }}
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
        layout={{ chars_per_line: 20, max_lines: 2, sentence_breaks: true, idle_reset_ms: 0 }}
        onChange={onChange}
      />,
    );

    await user.click(screen.getByLabelText("句尾換行"));

    expect(onChange).toHaveBeenLastCalledWith({
      chars_per_line: 20,
      max_lines: 2,
      sentence_breaks: false,
      idle_reset_ms: 0,
    });
  });

  it("說明門檻是剩餘空間而不是比例", () => {
    render(
      <CaptionLayoutSettings
        layout={{ chars_per_line: 20, max_lines: 2, sentence_breaks: true, idle_reset_ms: 0 }}
        onChange={vi.fn()}
      />,
    );
    expect(
      screen.getByText(/剩下不足 4 個全形字/),
    ).toBeInTheDocument();
  });
});

describe("停頓後重新開始", () => {
  it("送出毫秒值，其餘版面設定不變", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <CaptionLayoutSettings
        layout={{
          chars_per_line: 20,
          max_lines: 5,
          sentence_breaks: true,
          idle_reset_ms: 0,
        }}
        onChange={onChange}
      />,
    );

    const idle = screen.getByLabelText("停頓後重新開始（毫秒）");
    await user.clear(idle);
    await user.type(idle, "2500");

    expect(onChange).toHaveBeenLastCalledWith({
      chars_per_line: 20,
      max_lines: 5,
      sentence_breaks: true,
      idle_reset_ms: 2500,
    });
  });

  it("0 與門檻之間的值不送出，伺服器會拒絕", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <CaptionLayoutSettings
        layout={{
          chars_per_line: 20,
          max_lines: 2,
          sentence_breaks: true,
          idle_reset_ms: 0,
        }}
        onChange={onChange}
      />,
    );

    const idle = screen.getByLabelText("停頓後重新開始（毫秒）");
    await user.clear(idle);
    await user.type(idle, "100");

    expect(onChange).not.toHaveBeenCalledWith(
      expect.objectContaining({ idle_reset_ms: 100 }),
    );
  });

  it("關閉時標示為關閉，操作者不必記得 0 的意思", () => {
    render(
      <CaptionLayoutSettings
        layout={{
          chars_per_line: 20,
          max_lines: 2,
          sentence_breaks: true,
          idle_reset_ms: 0,
        }}
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByText("關閉")).toBeInTheDocument();
  });
});
