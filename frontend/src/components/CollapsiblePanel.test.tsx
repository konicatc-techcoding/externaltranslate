import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { CollapsiblePanel } from "./CollapsiblePanel";

describe("CollapsiblePanel", () => {
  it("預設收起，點標題展開", async () => {
    const user = userEvent.setup();
    render(
      <CollapsiblePanel title="環境檢查">
        <p>內容</p>
      </CollapsiblePanel>,
    );
    const panel = screen.getByText("環境檢查").closest("details") as HTMLDetailsElement;
    expect(panel.open).toBe(false);

    await user.click(screen.getByText("環境檢查"));

    expect(panel.open).toBe(true);
  });

  it("收起時仍看得到摘要", () => {
    render(
      <CollapsiblePanel title="環境檢查" summary="全部就緒">
        <p>內容</p>
      </CollapsiblePanel>,
    );

    expect(screen.getByText("全部就緒")).toBeInTheDocument();
  });

  it("出問題時自動展開", () => {
    // Tidying the page is not worth hiding a fault.
    render(
      <CollapsiblePanel title="環境檢查" openOnProblem>
        <p>內容</p>
      </CollapsiblePanel>,
    );
    const panel = screen.getByText("環境檢查").closest("details") as HTMLDetailsElement;

    expect(panel.open).toBe(true);
  });

  it("展開後使用者仍可自行收起", async () => {
    const user = userEvent.setup();
    render(
      <CollapsiblePanel title="環境檢查" openOnProblem>
        <p>內容</p>
      </CollapsiblePanel>,
    );
    const panel = screen.getByText("環境檢查").closest("details") as HTMLDetailsElement;

    await user.click(screen.getByText("環境檢查"));

    expect(panel.open).toBe(false);
  });
});
