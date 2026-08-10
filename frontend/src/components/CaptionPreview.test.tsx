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
    lines: ["你好"],
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
    const payload = caption({
      text: "<script>alert(1)</script>",
      lines: ["<script>alert(1)</script>"],
    });
    const { container } = render(<CaptionPreview caption={payload} />);

    expect(screen.getByText("<script>alert(1)</script>")).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
    expect(container.innerHTML).toContain("&lt;script&gt;");
  });

  it("空字幕顯示提示，overlay 模式則不顯示", () => {
    const empty = caption({ text: "", status: "idle", lines: [] });
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

  it("關閉滑動時不套用動畫", () => {
    const { rerender } = render(
      <CaptionPreview caption={caption({ lines: ["第一行"] })} scroll={false} />,
    );
    rerender(
      <CaptionPreview
        caption={caption({ lines: ["第一行", "第二行"] })}
        scroll={false}
      />,
    );
    expect(screen.getByTestId("caption-viewport").className).not.toContain(
      "sliding",
    );
  });

  it("視窗滿了、最上面那行被擠掉時才滑動", () => {
    const { rerender } = render(
      <CaptionPreview
        caption={caption({ lines: ["第一行", "第二行", "第三行"] })}
        maxLines={3}
        scroll
      />,
    );
    rerender(
      <CaptionPreview
        caption={caption({ lines: ["第二行", "第三行", "第四行"] })}
        maxLines={3}
        scroll
      />,
    );
    expect(screen.getByTestId("caption-viewport").className).toContain("sliding");
  });

  it("視窗還沒填滿時多一行不滑動", () => {
    // Lines stack from the top, so a new line appears in empty space below and
    // nothing above it moves. Sliding here would shove already-read text up and
    // back down for no reason — that is the shiver, not the effect.
    const { rerender } = render(
      <CaptionPreview
        caption={caption({ lines: ["第一行"] })}
        maxLines={3}
        scroll
      />,
    );
    rerender(
      <CaptionPreview
        caption={caption({ lines: ["第一行", "第二行"] })}
        maxLines={3}
        scroll
      />,
    );
    expect(screen.getByTestId("caption-viewport").className).not.toContain(
      "sliding",
    );
  });

  it("標點被拉回上一行時不滑動", () => {
    // The formatter pulls a closing mark back rather than letting it open a
    // line, so the top line's text grows without anything scrolling.
    const { rerender } = render(
      <CaptionPreview
        caption={caption({ lines: ["我們現在開始", "請看"] })}
        maxLines={3}
        scroll
      />,
    );
    rerender(
      <CaptionPreview
        caption={caption({ lines: ["我們現在開始。", "請看"] })}
        maxLines={3}
        scroll
      />,
    );
    expect(screen.getByTestId("caption-viewport").className).not.toContain(
      "sliding",
    );
  });

  it("只顯示一行時換句仍然滑動", () => {
    const { rerender } = render(
      <CaptionPreview
        caption={caption({ lines: ["前一句"] })}
        maxLines={1}
        scroll
      />,
    );
    rerender(
      <CaptionPreview
        caption={caption({ lines: ["下一句"] })}
        maxLines={1}
        scroll
      />,
    );
    expect(screen.getByTestId("caption-viewport").className).toContain("sliding");
  });

  it("最後一行逐字增長不觸發滑動", () => {
    const { rerender } = render(
      <CaptionPreview caption={caption({ lines: ["第一行", "第二"] })} scroll />,
    );
    rerender(
      <CaptionPreview caption={caption({ lines: ["第一行", "第二行"] })} scroll />,
    );
    // partial fragments arrive several times a second; animating them would
    // make the caption shiver
    expect(screen.getByTestId("caption-viewport").className).not.toContain(
      "sliding",
    );
  });

  it("斷線時不滑動", () => {
    const { rerender } = render(
      <CaptionPreview caption={caption({ lines: ["第一行"] })} scroll />,
    );
    rerender(
      <CaptionPreview
        caption={caption({ lines: ["第一行", "第二行"] })}
        scroll
        stale
      />,
    );
    expect(screen.getByTestId("caption-viewport").className).not.toContain(
      "sliding",
    );
  });

  it("滑動時間傳進 CSS 變數", () => {
    render(
      <CaptionPreview caption={caption()} scroll scrollMs={400} />,
    );
    const box = screen.getByTestId("caption-viewport").parentElement as HTMLElement;
    expect(box.style.getPropertyValue("--caption-scroll-ms")).toBe("400ms");
  });

  it("行數換算為固定高度且裁切溢出內容", () => {
    render(
      <CaptionPreview
        caption={caption()}
        style={parseOverlayStyle(new URLSearchParams("size=40"))}
        maxLines={3}
      />,
    );
    const viewport = screen.getByTestId("caption-viewport");
    const box = viewport.parentElement as HTMLElement;

    expect(box.style.getPropertyValue("--caption-height")).toBe("156.00px");
    expect(box.style.getPropertyValue("--caption-bg")).toBe("rgba(0, 0, 0, 0.5)");
  });
});
