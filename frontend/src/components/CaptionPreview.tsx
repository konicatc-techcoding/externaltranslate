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
}: CaptionPreviewProps) {
  const lines = caption.lines ?? [];
  const visible = maxLines === undefined ? lines : lines.slice(-maxLines);
  const height = Math.max(1, maxLines ?? lines.length ?? 1);
  const hasText = visible.length > 0;

  return (
    <div
      className={`caption-box${stale ? " caption-box--stale" : ""}`}
      style={toCssVariables(style, height)}
      data-caption-status={caption.status}
      data-stale={stale ? "true" : "false"}
    >
      <div className="caption-box__viewport" data-testid="caption-viewport">
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
