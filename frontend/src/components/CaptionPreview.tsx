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

const SLIDE_CLASS = [
  "",
  " caption-box__viewport--sliding",
  " caption-box__viewport--sliding caption-box__viewport--sliding-b",
] as const;

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

  // 0 is "not sliding"; 1 and 2 are the same animation under two names. Setting
  // the same class again does not restart a CSS animation, so a second line
  // scrolling before the first animation finished would show no motion at all
  // and then snap when the first timer removed the class. Alternating the name
  // restarts it.
  const [slide, setSlide] = useState<0 | 1 | 2>(0);
  const previousFirstLine = useRef<string | undefined>(visible[0]);
  const previousCount = useRef(visible.length);

  useEffect(() => {
    const first = visible[0];
    const previous = previousFirstLine.current;
    // Scrolling never removes a line: the window is full and stays full. A
    // shorter window means the caption was replaced — `caption.idle_reset_ms`
    // starting a new one after a pause, or a clear — and sliding would drag
    // the new sentence up from below as if it had been pushed.
    const shrank = visible.length < previousCount.current;
    previousFirstLine.current = first;
    previousCount.current = visible.length;

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
      !shrank &&
      !first.startsWith(previous);

    if (!scroll || stale || !scrolledPastTheTop) {
      return;
    }
    setSlide((current) => (current === 1 ? 2 : 1));
    const timer = window.setTimeout(() => setSlide(0), scrollMs);
    return () => window.clearTimeout(timer);
    // `visible.length` is a dependency so the count stays current even on the
    // renders that do not change the top line; otherwise `shrank` would be
    // measured against a stale count.
  }, [visible[0], visible.length, scroll, stale, scrollMs]);

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
        className={`caption-box__viewport${SLIDE_CLASS[slide]}`}
        data-testid="caption-viewport"
      >
        {hasText ? (
          visible.map((line, index) => (
            // Keyed by position alone. Including the text would give a line a
            // new identity every time a fragment lands, so React would throw
            // the element away and build another one several times a second —
            // a teardown the browser has to repaint, mid-animation.
            <p className="caption-box__text" key={index}>
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
