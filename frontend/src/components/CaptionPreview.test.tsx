import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CaptionPreview } from "./CaptionPreview";
import { parseOverlayStyle } from "../overlay/style";
import type { CaptionPayload } from "../types/runtime";

function caption(overrides: Partial<CaptionPayload> = {}): CaptionPayload {
  return {
    revision: 1,
    status: "partial",
    text: "你好",
    language_code: "zh-Hant",
    updated_at: 1,
    session_generation: 1,
    ...overrides,
  };
}

describe("CaptionPreview", () => {
  it("以文字節點顯示字幕", () => {
    render(<CaptionPreview caption={caption()} />);
    expect(screen.getByText("你好")).toBeInTheDocument();
  });

  it("含 HTML 的字幕顯示為純文字", () => {
    const payload = caption({ text: "<script>alert(1)</script>" });
    const { container } = render(<CaptionPreview caption={payload} />);

    expect(screen.getByText("<script>alert(1)</script>")).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
    expect(container.innerHTML).toContain("&lt;script&gt;");
  });

  it("空字幕顯示提示，overlay 模式則不顯示", () => {
    const empty = caption({ text: "", status: "idle" });
    const { rerender } = render(<CaptionPreview caption={empty} />);
    expect(screen.getByText("尚無字幕")).toBeInTheDocument();

    rerender(<CaptionPreview caption={empty} showEmptyHint={false} />);
    expect(screen.queryByText("尚無字幕")).not.toBeInTheDocument();
  });

  it("stale 時標記為過期但保留最後字幕", () => {
    const { container } = render(<CaptionPreview caption={caption()} stale />);
    expect(screen.getByText("你好")).toBeInTheDocument();
    expect(container.querySelector('[data-stale="true"]')).not.toBeNull();
  });

  it("行數換算為固定高度且裁切溢出內容", () => {
    render(
      <CaptionPreview
        caption={caption()}
        style={parseOverlayStyle(new URLSearchParams("lines=3&size=40"))}
      />,
    );
    const viewport = screen.getByTestId("caption-viewport");
    const box = viewport.parentElement as HTMLElement;

    expect(box.style.getPropertyValue("--caption-height")).toBe("156.00px");
    expect(box.style.getPropertyValue("--caption-bg")).toBe("rgba(0, 0, 0, 0.5)");
  });
});
