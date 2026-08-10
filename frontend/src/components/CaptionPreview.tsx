import { useEffect, useRef, useState } from "react";

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
  /** Display height in lines; defaults to however many lines arrived. */
  maxLines?: number;
  /** Slide new lines in instead of letting them jump into place. */
  scroll?: boolean;
  scrollMs?: number;
}

/**
 * Caption text is rendered as text nodes. React escapes it, and nothing here
 * ever touches innerHTML, so provider output cannot become markup.
 *
 * Line breaking is **not** done here: the backend formatter produces
 * `caption.lines`, and every consumer renders those same lines so the web
 * overlay and the vMix GT title cannot wrap differently.
 */
export function CaptionPreview({
  caption,
  stale = false,
  style = DEFAULT_OVERLAY_STYLE,
  showEmptyHint = true,
  maxLines,
  scroll = false,
  scrollMs = 250,
}: CaptionPreviewProps) {
  const lines = caption.lines ?? [];
  const visible = maxLines === undefined ? lines : lines.slice(-maxLines);
  const height = Math.max(1, maxLines ?? lines.length ?? 1);
  const hasText = visible.length > 0;

  const [sliding, setSliding] = useState(false);
  const previousFirstLine = useRef<string | undefined>(visible[0]);

  useEffect(() => {
    const first = visible[0];
    const previous = previousFirstLine.current;
    previousFirstLine.current = first;

    // Slide only when the top line was *replaced*, which is the only time
    // anything actually scrolls past the top edge. Two things change the top
    // line without scrolling: a closing mark pulled back onto it by the
    // formatter, and a new line appearing in the empty space below while the
    // window is not yet full. Text is only ever appended, so an edited line
    // still starts with what it said before — that prefix is what tells the
    // two cases apart. Animating them shoves already-read text up and back,
    // which reads as a shiver rather than a scroll.
    const scrolledPastTheTop =
      previous !== undefined &&
      first !== undefined &&
      !first.startsWith(previous);

    if (!scroll || stale || !scrolledPastTheTop) {
      return;
    }
    setSliding(true);
    const timer = window.setTimeout(() => setSliding(false), scrollMs);
    return () => window.clearTimeout(timer);
  }, [visible[0], scroll, stale, scrollMs]);

  return (
    <div
      className={`caption-box${stale ? " caption-box--stale" : ""}`}
      style={{
        ...toCssVariables(style, height),
        ["--caption-scroll-ms" as string]: `${scrollMs}ms`,
      }}
      data-caption-status={caption.status}
      data-stale={stale ? "true" : "false"}
    >
      <div
        className={`caption-box__viewport${sliding ? " caption-box__viewport--sliding" : ""}`}
        data-testid="caption-viewport"
      >
        {hasText ? (
          visible.map((line, index) => (
            // Lines have no stable identity; position is the only key there is.
            <p className="caption-box__text" key={`${index}-${line}`}>
              {line}
            </p>
          ))
        ) : showEmptyHint ? (
          <p className="caption-box__placeholder">{zhTW.caption.empty}</p>
        ) : null}
      </div>
    </div>
  );
}
