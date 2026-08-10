import { useEffect, useRef } from "react";

import { zhTW } from "../i18n/zh-TW";
import {
  DEFAULT_OVERLAY_STYLE,
  toCssVariables,
  type OverlayStyle,
} from "../overlay/style";
import type { CaptionPayload } from "../types/runtime";

interface CaptionPreviewProps {
  caption: CaptionPayload;
  stale?: boolean;
  style?: OverlayStyle;
  showEmptyHint?: boolean;
}

/**
 * Caption text is rendered as a text node. React escapes it, and nothing here
 * ever touches innerHTML, so provider output cannot become markup.
 */
export function CaptionPreview({
  caption,
  stale = false,
  style = DEFAULT_OVERLAY_STYLE,
  showEmptyHint = true,
}: CaptionPreviewProps) {
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const box = boxRef.current;
    if (box !== null) {
      // Stick to the newest line: the box shows the last `lines` of a caption
      // that keeps growing.
      box.scrollTop = box.scrollHeight;
    }
  }, [caption.text, caption.revision]);

  const hasText = caption.text.length > 0;

  return (
    <div
      className={`caption-box${stale ? " caption-box--stale" : ""}`}
      style={toCssVariables(style)}
      data-caption-status={caption.status}
      data-stale={stale ? "true" : "false"}
    >
      <div className="caption-box__viewport" ref={boxRef} data-testid="caption-viewport">
        {hasText ? (
          <p className="caption-box__text">{caption.text}</p>
        ) : showEmptyHint ? (
          <p className="caption-box__placeholder">{zhTW.caption.empty}</p>
        ) : null}
      </div>
    </div>
  );
}
