import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ShutdownButton } from "./ShutdownButton";

describe("ShutdownButton", () => {
  it("按下不會直接關閉，要先確認", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<ShutdownButton running={false} onConfirm={onConfirm} />);

    await user.click(screen.getByRole("button", { name: "關閉程式" }));

    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "確定關閉" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "確定關閉" }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("取消後什麼也不做", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<ShutdownButton running={false} onConfirm={onConfirm} />);

    await user.click(screen.getByRole("button", { name: "關閉程式" }));
    await user.click(screen.getByRole("button", { name: "取消" }));

    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("翻譯進行中要講清楚會中斷", async () => {
    const user = userEvent.setup();
    render(<ShutdownButton running onConfirm={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "關閉程式" }));

    expect(screen.getByText(/翻譯正在進行中/)).toBeInTheDocument();
  });
});
