import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OverlayPage } from "./OverlayPage";
import { IDLE_RUNTIME_STATUS } from "../types/runtime";

const sockets: FakeSocket[] = [];

class FakeSocket {
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor() {
    sockets.push(this);
  }

  close(): void {
    this.closed = true;
  }
}

function pushCaption(text: string, status: "partial" | "final" = "partial"): void {
  // The socket callback updates React state from outside an event handler.
  act(() => {
    sockets[0].onmessage?.({
      data: JSON.stringify({
        ...IDLE_RUNTIME_STATUS,
        running: true,
        caption: {
          ...IDLE_RUNTIME_STATUS.caption,
          revision: 1,
          status,
          text,
          lines: [text],
        },
      }),
    });
  });
}

function dropSocket(): void {
  act(() => {
    sockets[0].onclose?.();
  });
}

beforeEach(() => {
  sockets.length = 0;
  vi.stubGlobal("WebSocket", FakeSocket);
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.className = "";
});

describe("OverlayPage", () => {
  it("頁面背景保持透明供 vMix/OBS 去背", () => {
    render(<OverlayPage search="" />);
    expect(document.body.classList.contains("overlay-body")).toBe(true);
  });

  it("顯示字幕但沒有控制項", () => {
    render(<OverlayPage search="" />);
    pushCaption("你好");

    expect(screen.getByText("你好")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("套用 query 樣式參數", () => {
    render(<OverlayPage search="?lines=3&size=40&bg=%23112233&opacity=0&align=left" />);
    pushCaption("你好");

    const box = screen.getByTestId("caption-viewport").parentElement as HTMLElement;
    expect(box.style.getPropertyValue("--caption-height")).toBe("156.00px");
    expect(box.style.getPropertyValue("--caption-bg")).toBe("rgba(17, 34, 51, 0)");
    expect(box.style.getPropertyValue("--caption-align")).toBe("left");
  });

  it("非法參數 fail closed 回預設", () => {
    render(<OverlayPage search="?size=9999&color=red&font=evil" />);
    pushCaption("你好");

    const box = screen.getByTestId("caption-viewport").parentElement as HTMLElement;
    expect(box.style.getPropertyValue("--caption-size")).toBe("48px");
    expect(box.style.getPropertyValue("--caption-color")).toBe("#FFFFFF");
    expect(box.style.getPropertyValue("--caption-font")).toContain("Microsoft JhengHei");
  });

  it("斷線時保留最後字幕並標示過期", () => {
    render(<OverlayPage search="" />);
    pushCaption("你好嗎");
    dropSocket();

    expect(screen.getByText("你好嗎")).toBeInTheDocument();
    const box = screen.getByTestId("caption-viewport").parentElement as HTMLElement;
    expect(box.dataset.stale).toBe("true");
  });

  it("預設顯示後端排好的行，行數依後端版面", () => {
    render(<OverlayPage search="" />);
    act(() => {
      sockets[0].onmessage?.({
        data: JSON.stringify({
          ...IDLE_RUNTIME_STATUS,
          running: true,
          layout: { chars_per_line: 4, max_lines: 2 },
          caption: {
            ...IDLE_RUNTIME_STATUS.caption,
            revision: 1,
            status: "partial",
            text: "一二三四五六七八",
            lines: ["一二三四", "五六七八"],
          },
        }),
      });
    });

    expect(screen.getByText("一二三四")).toBeInTheDocument();
    expect(screen.getByText("五六七八")).toBeInTheDocument();
  });

  it("lines 參數只覆寫本頁顯示行數，不改後端排版", () => {
    render(<OverlayPage search="?lines=1" />);
    act(() => {
      sockets[0].onmessage?.({
        data: JSON.stringify({
          ...IDLE_RUNTIME_STATUS,
          running: true,
          layout: { chars_per_line: 4, max_lines: 3 },
          caption: {
            ...IDLE_RUNTIME_STATUS.caption,
            revision: 1,
            status: "partial",
            text: "一二三四五六七八",
            lines: ["一二三四", "五六七八"],
          },
        }),
      });
    });

    // only the newest line is shown here; the backend still produced two
    expect(screen.queryByText("一二三四")).toBeNull();
    expect(screen.getByText("五六七八")).toBeInTheDocument();
  });

  it("後端的描邊與內距直接套用到 overlay", () => {
    render(<OverlayPage search="" />);
    act(() => {
      sockets[0].onmessage?.({
        data: JSON.stringify({
          ...IDLE_RUNTIME_STATUS,
          running: true,
          style: {
            ...IDLE_RUNTIME_STATUS.style,
            outline_width: 4,
            outline_color: "#101010",
            padding: 30,
            radius: 20,
            weight: "bold",
            align: "center",
          },
          caption: {
            ...IDLE_RUNTIME_STATUS.caption,
            revision: 1,
            status: "partial",
            text: "你好",
            lines: ["你好"],
          },
        }),
      });
    });

    const box = screen.getByTestId("caption-viewport").parentElement as HTMLElement;
    expect(box.style.getPropertyValue("--caption-text-shadow")).toContain("#101010");
    expect(box.style.getPropertyValue("--caption-padding")).toBe("30px");
    expect(box.style.getPropertyValue("--caption-radius")).toBe("20px");
    expect(box.style.getPropertyValue("--caption-weight")).toBe("bold");
    expect(box.style.getPropertyValue("--caption-align")).toBe("center");
  });

  it("query 參數勝過後端設定，僅限這一頁", () => {
    render(<OverlayPage search="?outline=0&align=right" />);
    act(() => {
      sockets[0].onmessage?.({
        data: JSON.stringify({
          ...IDLE_RUNTIME_STATUS,
          style: { ...IDLE_RUNTIME_STATUS.style, outline_width: 6, align: "center" },
          caption: {
            ...IDLE_RUNTIME_STATUS.caption,
            revision: 1,
            status: "partial",
            text: "你好",
            lines: ["你好"],
          },
        }),
      });
    });

    const box = screen.getByTestId("caption-viewport").parentElement as HTMLElement;
    expect(box.style.getPropertyValue("--caption-text-shadow")).toBe("none");
    expect(box.style.getPropertyValue("--caption-align")).toBe("right");
  });

  it("空字幕不顯示提示字", () => {
    render(<OverlayPage search="" />);
    expect(screen.queryByText("尚無字幕")).toBeNull();
  });
});
