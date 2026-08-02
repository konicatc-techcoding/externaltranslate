import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("App", () => {
  it("顯示繁體中文的 Stage 0 初始狀態", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "ExternalTranslate" })).toBeInTheDocument();
    expect(screen.getByText("即時翻譯字幕控制台")).toBeInTheDocument();
    expect(screen.getByText("尚未檢查環境")).toBeInTheDocument();
  });
});
