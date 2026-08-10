import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TranslationClock, formatDuration } from "./TranslationClock";

describe("formatDuration", () => {
  it("以時:分:秒呈現", () => {
    expect(formatDuration(0)).toBe("00:00:00");
    expect(formatDuration(9)).toBe("00:00:09");
    expect(formatDuration(75)).toBe("00:01:15");
    expect(formatDuration(3600)).toBe("01:00:00");
    expect(formatDuration(3661.9)).toBe("01:01:01");
    expect(formatDuration(45296)).toBe("12:34:56");
  });

  it("負值不會顯示成負時間", () => {
    expect(formatDuration(-5)).toBe("00:00:00");
  });
});

describe("TranslationClock", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("執行中會持續往上數，即使沒有新的 snapshot", () => {
    let now = 10_000;
    render(
      <TranslationClock elapsedSeconds={5} running now={() => now} />,
    );
    expect(screen.getByLabelText("本次翻譯已進行時間")).toHaveTextContent("00:00:05");

    act(() => {
      now = 13_000;
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByLabelText("本次翻譯已進行時間")).toHaveTextContent("00:00:08");
  });

  it("停止後保留最後時間且不再前進", () => {
    let now = 10_000;
    const { rerender } = render(
      <TranslationClock elapsedSeconds={5} running now={() => now} />,
    );

    now = 12_000;
    rerender(<TranslationClock elapsedSeconds={7} running={false} now={() => now} />);
    expect(screen.getByLabelText("本次翻譯已進行時間")).toHaveTextContent("00:00:07");

    act(() => {
      now = 60_000;
      vi.advanceTimersByTime(5000);
    });
    expect(screen.getByLabelText("本次翻譯已進行時間")).toHaveTextContent("00:00:07");
  });

  it("重新開始時從新的 snapshot 值繼續，不累加上一輪", () => {
    let now = 10_000;
    const { rerender } = render(
      <TranslationClock elapsedSeconds={30} running={false} now={() => now} />,
    );
    expect(screen.getByLabelText("本次翻譯已進行時間")).toHaveTextContent("00:00:30");

    now = 20_000;
    rerender(<TranslationClock elapsedSeconds={0} running now={() => now} />);
    expect(screen.getByLabelText("本次翻譯已進行時間")).toHaveTextContent("00:00:00");
  });

  it("停止後不再保留計時器", () => {
    const clearSpy = vi.spyOn(window, "clearInterval");
    const { rerender, unmount } = render(
      <TranslationClock elapsedSeconds={1} running now={() => 0} />,
    );
    rerender(<TranslationClock elapsedSeconds={1} running={false} now={() => 0} />);
    expect(clearSpy).toHaveBeenCalled();
    unmount();
  });
});
