import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApiKeyField } from "./ApiKeyField";

const KEY = "AIzaSyFAKEKEYFAKEKEY";

describe("ApiKeyField", () => {
  it("預設遮蔽輸入並可切換顯示", async () => {
    const user = userEvent.setup();
    render(
      <ApiKeyField
        configured={false}
        onSubmit={vi.fn()}
        onTest={vi.fn()}
        onClear={vi.fn()}
      />,
    );
    const input = screen.getByLabelText("API Key 輸入欄");
    expect(input).toHaveAttribute("type", "password");

    await user.click(screen.getByRole("button", { name: "顯示" }));
    expect(screen.getByLabelText("API Key 輸入欄")).toHaveAttribute("type", "text");
  });

  it("送出後保留遮罩點，讓使用者看得出已儲存", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    const { rerender } = render(
      <ApiKeyField
        configured={false}
        onSubmit={onSubmit}
        onTest={vi.fn()}
        onClear={vi.fn()}
      />,
    );

    await user.type(screen.getByLabelText("API Key 輸入欄"), KEY);
    await user.click(screen.getByRole("button", { name: "儲存" }));
    expect(onSubmit).toHaveBeenCalledWith(KEY);

    // the parent flips `configured` once the local service accepted the key
    rerender(
      <ApiKeyField
        configured
        onSubmit={onSubmit}
        onTest={vi.fn()}
        onClear={vi.fn()}
      />,
    );

    const input = screen.getByLabelText("API Key 輸入欄");
    expect(input).toHaveAttribute("readonly");
    expect(input).toHaveAttribute("type", "password");
    const shown = (input as HTMLInputElement).value;
    expect(shown).not.toBe("");
    // the dots are a fixed placeholder: neither the key nor its length
    expect(shown).not.toContain(KEY);
    expect(shown).toEqual("•".repeat(shown.length));
    expect(shown.length).not.toBe(KEY.length);
  });

  it("儲存後不寫入瀏覽器儲存空間", async () => {
    const user = userEvent.setup();
    render(
      <ApiKeyField
        configured={false}
        onSubmit={vi.fn()}
        onTest={vi.fn()}
        onClear={vi.fn()}
      />,
    );

    await user.type(screen.getByLabelText("API Key 輸入欄"), KEY);
    await user.click(screen.getByRole("button", { name: "儲存" }));

    const stored = [
      ...Object.values(window.localStorage),
      ...Object.values(window.sessionStorage),
      document.cookie,
    ].join("|");
    expect(stored).not.toContain(KEY);
  });

  it("已儲存時不能直接改寫，清除後恢復可輸入", async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <ApiKeyField
        configured
        onSubmit={vi.fn()}
        onTest={vi.fn()}
        onClear={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "儲存" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "顯示" })).toBeNull();

    rerender(
      <ApiKeyField
        configured={false}
        onSubmit={vi.fn()}
        onTest={vi.fn()}
        onClear={vi.fn()}
      />,
    );

    const input = screen.getByLabelText("API Key 輸入欄");
    expect(input).toHaveValue("");
    expect(input).not.toHaveAttribute("readonly");
    await user.type(input, "new-key");
    expect(screen.getByRole("button", { name: "儲存" })).toBeEnabled();
  });

  it("已設定時只顯示狀態，不顯示金鑰內容", () => {
    const { container } = render(
      <ApiKeyField
        configured
        onSubmit={vi.fn()}
        onTest={vi.fn()}
        onClear={vi.fn()}
      />,
    );
    expect(screen.getByText("已設定（只保留在本機程序記憶體）")).toBeInTheDocument();
    expect(container.textContent).not.toContain(KEY.slice(-4));
  });

  it("未設定時測試與清除為停用", () => {
    render(
      <ApiKeyField
        configured={false}
        onSubmit={vi.fn()}
        onTest={vi.fn()}
        onClear={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "測試連線" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "清除" })).toBeDisabled();
  });
});
