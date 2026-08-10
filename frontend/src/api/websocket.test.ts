import { describe, expect, it } from "vitest";

import { connectCaptionSocket, type SocketLike, type SocketState } from "./websocket";
import { IDLE_RUNTIME_STATUS } from "../types/runtime";

class FakeSocket implements SocketLike {
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  close(): void {
    this.closed = true;
  }
}

function harness() {
  const sockets: FakeSocket[] = [];
  const states: SocketState[] = [];
  const snapshots: unknown[] = [];
  const scheduled: Array<{ callback: () => void; delayMs: number }> = [];

  const handle = connectCaptionSocket({
    url: "ws://127.0.0.1:8765/ws/captions",
    onSnapshot: (status) => snapshots.push(status),
    onState: (state) => states.push(state),
    createSocket: () => {
      const socket = new FakeSocket();
      sockets.push(socket);
      return socket;
    },
    schedule: (callback, delayMs) => scheduled.push({ callback, delayMs }),
    delays: [500, 1000],
  });

  return { sockets, states, snapshots, scheduled, handle };
}

describe("caption socket", () => {
  it("開啟後回報 open 並轉交 snapshot", () => {
    const { sockets, states, snapshots } = harness();
    sockets[0].onopen?.();
    sockets[0].onmessage?.({ data: JSON.stringify(IDLE_RUNTIME_STATUS) });

    expect(states).toEqual(["connecting", "open"]);
    expect(snapshots).toEqual([IDLE_RUNTIME_STATUS]);
  });

  it("斷線時標記 stale 並以退避重連", () => {
    const { sockets, states, scheduled } = harness();
    sockets[0].onopen?.();
    sockets[0].onclose?.();

    expect(states).toEqual(["connecting", "open", "stale"]);
    expect(scheduled[0].delayMs).toBe(500);

    scheduled[0].callback();
    sockets[1].onclose?.();
    expect(scheduled[1].delayMs).toBe(1000);

    scheduled[1].callback();
    sockets[2].onclose?.();
    // delay list is exhausted, so the last delay repeats as the cap
    expect(scheduled[2].delayMs).toBe(1000);
  });

  it("重新連上後退避重新計算", () => {
    const { sockets, scheduled } = harness();
    sockets[0].onclose?.();
    scheduled[0].callback();
    sockets[1].onopen?.();
    sockets[1].onclose?.();

    expect(scheduled[1].delayMs).toBe(500);
  });

  it("壞掉的訊息不會中斷連線", () => {
    const { sockets, snapshots, states } = harness();
    sockets[0].onopen?.();
    sockets[0].onmessage?.({ data: "not json" });

    expect(snapshots).toEqual([]);
    expect(states).toEqual(["connecting", "open"]);
  });

  it("呼叫端關閉後不再重連", () => {
    const { sockets, scheduled, handle } = harness();
    handle.close();
    sockets[0].onclose?.();

    expect(sockets[0].closed).toBe(true);
    expect(scheduled).toEqual([]);
  });
});
