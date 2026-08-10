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
export const OUTLINE_RANGE = [0, 8] as const;
export const PADDING_RANGE = [0, 64] as const;
export const RADIUS_RANGE = [0, 48] as const;

/** Fonts the playout machine may not have installed. */
const NEEDS_INSTALL = new Set(["noto-sans-tc"]);

type NumericKey =
  | "size"
  | "scroll_ms"
  | "outline_width"
  | "padding"
  | "radius";

const RANGES: Record<NumericKey, readonly [number, number]> = {
  size: SIZE_RANGE,
  scroll_ms: SCROLL_MS_RANGE,
  outline_width: OUTLINE_RANGE,
  padding: PADDING_RANGE,
  radius: RADIUS_RANGE,
};

/**
 * Overlay appearance. Like the layout panel this applies live, and the
 * server's reported values win so a correction or another client's change is
 * always reflected.
 */
export function CaptionStyleSettings({
  style,
  onChange,
}: CaptionStyleSettingsProps) {
  // Numeric fields are edited as text so a half-typed value ("6" on the way to
  // "64") is not immediately rejected and snapped back.
  const [drafts, setDrafts] = useState<Record<NumericKey, string>>({
    size: String(style.size),
    scroll_ms: String(style.scroll_ms),
    outline_width: String(style.outline_width),
    padding: String(style.padding),
    radius: String(style.radius),
  });

  useEffect(() => {
    setDrafts({
      size: String(style.size),
      scroll_ms: String(style.scroll_ms),
      outline_width: String(style.outline_width),
      padding: String(style.padding),
      radius: String(style.radius),
    });
  }, [
    style.size,
    style.scroll_ms,
    style.outline_width,
    style.padding,
    style.radius,
  ]);

  const commit = (next: Partial<CaptionStyle>): void => {
    onChange({ ...style, ...next });
  };

  const editNumber = (key: NumericKey, raw: string): void => {
    setDrafts((current) => ({ ...current, [key]: raw }));
    const [min, max] = RANGES[key];
    const value = Number(raw);
    if (!Number.isInteger(value) || value < min || value > max) {
      return;
    }
    commit({ [key]: value } as Partial<CaptionStyle>);
  };

  const numberField = (key: NumericKey, label: string, step = 1) => {
    const [min, max] = RANGES[key];
    return (
      <>
        <label htmlFor={`caption-${key}`}>{label}</label>
        <input
          id={`caption-${key}`}
          type="number"
          inputMode="numeric"
          min={min}
          max={max}
          step={step}
          value={drafts[key]}
          onChange={(event) => editNumber(key, event.target.value)}
        />
      </>
    );
  };

  const colorField = (
    key: "color" | "outline_color" | "background_color",
    label: string,
  ) => (
    <>
      <label htmlFor={`caption-${key}`}>{label}</label>
      <input
        id={`caption-${key}`}
        type="color"
        value={style[key]}
        onChange={(event) =>
          commit({ [key]: event.target.value.toUpperCase() } as Partial<CaptionStyle>)
        }
      />
      <output>{style[key]}</output>
    </>
  );

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

        {numberField("size", zhTW.captionStyle.size)}

        <label>
          <input
            type="checkbox"
            checked={style.weight === "bold"}
            onChange={(event) =>
              commit({ weight: event.target.checked ? "bold" : "normal" })
            }
          />
          {zhTW.captionStyle.weight}
        </label>
      </div>

      <div className="field-row">
        {colorField("color", zhTW.captionStyle.color)}

        <label htmlFor="caption-align">{zhTW.captionStyle.align}</label>
        <select
          id="caption-align"
          value={style.align}
          onChange={(event) => commit({ align: event.target.value })}
        >
          <option value="left">{zhTW.captionStyle.alignLeft}</option>
          <option value="center">{zhTW.captionStyle.alignCenter}</option>
          <option value="right">{zhTW.captionStyle.alignRight}</option>
        </select>
      </div>

      {NEEDS_INSTALL.has(style.font) ? (
        <p className="panel__warning">{zhTW.captionStyle.fontWarning}</p>
      ) : null}

      <div className="field-row">
        {numberField("outline_width", zhTW.captionStyle.outlineWidth)}
        {colorField("outline_color", zhTW.captionStyle.outlineColor)}

        <label>
          <input
            type="checkbox"
            checked={style.shadow}
            onChange={(event) => commit({ shadow: event.target.checked })}
          />
          {zhTW.captionStyle.shadow}
        </label>
      </div>
      <p className="panel__note">{zhTW.captionStyle.outlineHint}</p>

      <div className="field-row">
        {colorField("background_color", zhTW.captionStyle.backgroundColor)}

        <label htmlFor="caption-background-opacity">
          {zhTW.captionStyle.backgroundOpacity}
        </label>
        <input
          id="caption-background-opacity"
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={style.background_opacity}
          onChange={(event) =>
            commit({ background_opacity: Number(event.target.value) })
          }
        />
        <output>{style.background_opacity.toFixed(2)}</output>
      </div>
      <p className="panel__note">{zhTW.captionStyle.backgroundHint}</p>

      <div className="field-row">
        {numberField("padding", zhTW.captionStyle.padding)}
        {numberField("radius", zhTW.captionStyle.radius)}
      </div>

      <div className="field-row">
        <label>
          <input
            type="checkbox"
            checked={style.scroll}
            onChange={(event) => commit({ scroll: event.target.checked })}
          />
          {zhTW.captionStyle.scroll}
        </label>

        <label htmlFor="caption-scroll_ms">{zhTW.captionStyle.scrollMs}</label>
        <input
          id="caption-scroll_ms"
          type="number"
          inputMode="numeric"
          min={SCROLL_MS_RANGE[0]}
          max={SCROLL_MS_RANGE[1]}
          step={10}
          value={drafts.scroll_ms}
          disabled={!style.scroll}
          onChange={(event) => editNumber("scroll_ms", event.target.value)}
        />
      </div>
    </section>
  );
}
