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
    expect(box.style.getPropertyValue("--caption-font")).toContain("Noto Sans TC");
  });

  it("斷線時保留最後字幕並標示過期", () => {
    render(<OverlayPage search="" />);
    pushCaption("你好嗎");
    dropSocket();

    expect(screen.getByText("你好嗎")).toBeInTheDocument();
    const box = screen.getByTestId("caption-viewport").parentElement as HTMLElement;
    expect(box.dataset.stale).toBe("true");
  });

  it("空字幕不顯示提示字", () => {
    render(<OverlayPage search="" />);
    expect(screen.queryByText("尚無字幕")).toBeNull();
  });
});
