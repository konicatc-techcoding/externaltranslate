import { useEffect, useState } from "react";

import { connectCaptionSocket, type SocketState } from "../api/websocket";
import { CaptionPreview } from "../components/CaptionPreview";
import { parseOverlayStyle } from "../overlay/style";
import { IDLE_RUNTIME_STATUS, type RuntimeStatus } from "../types/runtime";

interface OverlayPageProps {
  search?: string;
}

/**
 * Caption-only page for vMix Browser Input and OBS Browser Source. The page
 * background stays fully transparent so the host can key it out; only the
 * caption box carries the configured colour and opacity.
 */
export function OverlayPage({ search }: OverlayPageProps) {
  const [status, setStatus] = useState<RuntimeStatus>(IDLE_RUNTIME_STATUS);
  const [socketState, setSocketState] = useState<SocketState>("connecting");
  const params = new URLSearchParams(search ?? window.location.search);
  const style = parseOverlayStyle(params);
  // The backend layout decides how many lines exist; `lines` only overrides
  // how many this overlay shows, so two Browser Inputs can differ.
  const maxLines = params.has("lines") ? style.lines : status.layout.max_lines;

  useEffect(() => {
    document.body.classList.add("overlay-body");
    return () => document.body.classList.remove("overlay-body");
  }, []);

  useEffect(() => {
    const socket = connectCaptionSocket({
      onSnapshot: setStatus,
      onState: setSocketState,
    });
    return () => socket.close();
  }, []);

  return (
    <main className="overlay-shell">
      <CaptionPreview
        caption={status.caption}
        stale={socketState === "stale"}
        style={style}
        maxLines={maxLines}
        showEmptyHint={false}
      />
    </main>
  );
}
