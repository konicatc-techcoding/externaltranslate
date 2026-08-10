import { useEffect, useState } from "react";

import { zhTW } from "../i18n/zh-TW";
import { FONT_LABELS, FONT_STACKS } from "../overlay/style";
import type { CaptionStyle } from "../types/runtime";

interface CaptionStyleSettingsProps {
  style: CaptionStyle;
  onChange: (style: CaptionStyle) => void;
}

export const SIZE_RANGE = [12, 200] as const;
export const SCROLL_MS_RANGE = [120, 1000] as const;

/** Fonts the playout machine may not have installed. */
const NEEDS_INSTALL = new Set(["noto-sans-tc"]);

/**
 * Overlay appearance. Like the layout panel this applies live, and the
 * server's reported values win so a correction or another client's change is
 * always reflected.
 */
export function CaptionStyleSettings({
  style,
  onChange,
}: CaptionStyleSettingsProps) {
  const [size, setSize] = useState(String(style.size));
  const [scrollMs, setScrollMs] = useState(String(style.scroll_ms));

  useEffect(() => {
    setSize(String(style.size));
    setScrollMs(String(style.scroll_ms));
  }, [style.size, style.scroll_ms]);

  const commit = (next: Partial<CaptionStyle>): void => {
    onChange({ ...style, ...next });
  };

  const commitBounded = (
    raw: string,
    [min, max]: readonly [number, number],
    key: "size" | "scroll_ms",
  ): void => {
    const value = Number(raw);
    if (!Number.isInteger(value) || value < min || value > max) {
      return;
    }
    commit({ [key]: value } as Partial<CaptionStyle>);
  };

  return (
    <section className="panel" aria-labelledby="caption-style-title">
      <h2 id="caption-style-title">{zhTW.captionStyle.title}</h2>
      <p className="panel__note">{zhTW.captionStyle.note}</p>

      <div className="field-row">
        <label htmlFor="caption-font">{zhTW.captionStyle.font}</label>
        <select
          id="caption-font"
          value={style.font}
          onChange={(event) => commit({ font: event.target.value })}
        >
          {Object.keys(FONT_STACKS).map((key) => (
            <option key={key} value={key}>
              {FONT_LABELS[key] ?? key}
            </option>
          ))}
        </select>

        <label htmlFor="caption-size">{zhTW.captionStyle.size}</label>
        <input
          id="caption-size"
          type="number"
          inputMode="numeric"
          min={SIZE_RANGE[0]}
          max={SIZE_RANGE[1]}
          value={size}
          onChange={(event) => {
            setSize(event.target.value);
            commitBounded(event.target.value, SIZE_RANGE, "size");
          }}
        />
      </div>

      <div className="field-row">
        <label htmlFor="caption-color">{zhTW.captionStyle.color}</label>
        <input
          id="caption-color"
          type="color"
          value={style.color}
          onChange={(event) =>
            commit({ color: event.target.value.toUpperCase() })
          }
        />
        <output>{style.color}</output>
      </div>

      {NEEDS_INSTALL.has(style.font) ? (
        <p className="panel__warning">{zhTW.captionStyle.fontWarning}</p>
      ) : null}

      <div className="field-row">
        <label>
          <input
            type="checkbox"
            checked={style.scroll}
            onChange={(event) => commit({ scroll: event.target.checked })}
          />
          {zhTW.captionStyle.scroll}
        </label>

        <label htmlFor="scroll-ms">{zhTW.captionStyle.scrollMs}</label>
        <input
          id="scroll-ms"
          type="number"
          inputMode="numeric"
          min={SCROLL_MS_RANGE[0]}
          max={SCROLL_MS_RANGE[1]}
          step={10}
          value={scrollMs}
          disabled={!style.scroll}
          onChange={(event) => {
            setScrollMs(event.target.value);
            commitBounded(event.target.value, SCROLL_MS_RANGE, "scroll_ms");
          }}
        />
      </div>
    </section>
  );
}
