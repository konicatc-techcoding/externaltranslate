import type { RuntimeStatus } from "../types/runtime";

export type SocketState = "connecting" | "open" | "stale";

export interface SocketLike {
  onopen: (() => void) | null;
  onmessage: ((event: { data: string }) => void) | null;
  onclose: (() => void) | null;
  onerror: (() => void) | null;
  close: () => void;
}

export interface CaptionSocketOptions {
  url?: string;
  onSnapshot: (status: RuntimeStatus) => void;
  onState: (state: SocketState) => void;
  createSocket?: (url: string) => SocketLike;
  schedule?: (callback: () => void, delayMs: number) => void;
  delays?: readonly number[];
}

export const DEFAULT_RECONNECT_DELAYS = [500, 1000, 2000, 4000, 5000] as const;

function defaultUrl(): string {
  // In dev the socket bypasses the Vite proxy (its ws upgrade is unreliable)
  // and targets the backend directly; a production build is served by the
  // backend, so same-origin is correct there.
  const configured = import.meta.env.VITE_WS_URL;
  if (typeof configured === "string" && configured.length > 0) {
    return configured;
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws/captions`;
}

/**
 * Keep a caption socket open, marking the UI stale while it is down.
 *
 * A dropped socket must never look like "no captions": the last snapshot
 * stays on screen and the caller is told the data is stale.
 */
export function connectCaptionSocket(options: CaptionSocketOptions): {
  close: () => void;
} {
  const {
    onSnapshot,
    onState,
    createSocket = (url: string) => new WebSocket(url) as unknown as SocketLike,
    schedule = (callback, delayMs) => window.setTimeout(callback, delayMs),
    delays = DEFAULT_RECONNECT_DELAYS,
  } = options;

  let closedByCaller = false;
  let attempt = 0;
  let socket: SocketLike | null = null;

  const open = (): void => {
    if (closedByCaller) {
      return;
    }
    onState("connecting");
    const url = options.url ?? defaultUrl();
    socket = createSocket(url);
    socket.onopen = () => {
      attempt = 0;
      onState("open");
    };
    socket.onmessage = (event) => {
      try {
        onSnapshot(JSON.parse(event.data) as RuntimeStatus);
      } catch {
        // A malformed frame must not tear the socket down.
      }
    };
    socket.onclose = () => {
      if (closedByCaller) {
        return;
      }
      onState("stale");
      const delay = delays[Math.min(attempt, delays.length - 1)];
      attempt += 1;
      schedule(open, delay);
    };
    socket.onerror = () => {
      onState("stale");
    };
  };

  open();

  return {
    close: () => {
      closedByCaller = true;
      socket?.close();
    },
  };
}
