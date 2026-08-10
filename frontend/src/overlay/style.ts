import type { CSSProperties } from "react";

import type { CaptionStyle } from "../types/runtime";

export type OverlayAlign = "left" | "center" | "right";

/** The resolved shape the caption box renders from. */
export interface OverlayStyle {
  width: string;
  /** Display-height override in lines; the backend layout is the default. */
  lines: number;
  size: number;
  font: string;
  weight: string;
  color: string;
  outlineWidth: number;
  outlineColor: string;
  shadow: boolean;
  bg: string;
  opacity: number;
  padding: number;
  radius: number;
  align: OverlayAlign;
}

/**
 * Font families are a closed whitelist. A query parameter interpolated into
 * a CSS font stack would otherwise be an injection point, and a caption
 * overlay is pasted into vMix and OBS from URLs users copy around.
 */
export const FONT_STACKS: Record<string, string> = {
  jhenghei: '"Microsoft JhengHei", "Microsoft JhengHei UI", sans-serif',
  kai: '"DFKai-SB", "BiauKai", serif',
  // Not bundled with Windows; the playout machine must have it installed or
  // the browser silently falls back.
  "noto-sans-tc": '"Noto Sans TC", "Microsoft JhengHei", sans-serif',
};

export const FONT_LABELS: Record<string, string> = {
  jhenghei: "微軟正黑體",
  kai: "標楷體",
  "noto-sans-tc": "Noto Sans TC（需另行安裝）",
};

export const DEFAULT_OVERLAY_STYLE: OverlayStyle = {
  width: "90%",
  lines: 2,
  size: 48,
  font: FONT_STACKS.jhenghei,
  weight: "normal",
  color: "#FFFFFF",
  outlineWidth: 0,
  outlineColor: "#000000",
  shadow: false,
  bg: "#000000",
  opacity: 0.5,
  padding: 12,
  radius: 8,
  // Left by default: captions accumulate fragment by fragment, and centred
  // text reflows on every update so each word shifts sideways as the line
  // grows. Anchoring at the left edge keeps already-read text still.
  align: "left",
};

const HEX = /^#[0-9a-fA-F]{6}$/;
const PERCENT = /^\d{1,3}%$/;
const PIXELS = /^\d{2,5}$/;

/** Map the backend's appearance settings onto the render shape. */
export function captionStyleToOverlay(style: CaptionStyle): OverlayStyle {
  return {
    ...DEFAULT_OVERLAY_STYLE,
    lines: DEFAULT_OVERLAY_STYLE.lines,
    size: style.size,
    font: FONT_STACKS[style.font] ?? DEFAULT_OVERLAY_STYLE.font,
    weight: style.weight,
    color: style.color,
    outlineWidth: style.outline_width,
    outlineColor: style.outline_color,
    shadow: style.shadow,
    bg: style.background_color,
    opacity: style.background_opacity,
    padding: style.padding,
    radius: style.radius,
    align: (["left", "center", "right"] as const).includes(
      style.align as OverlayAlign,
    )
      ? (style.align as OverlayAlign)
      : DEFAULT_OVERLAY_STYLE.align,
  };
}

function parseWidth(raw: string): string | undefined {
  if (PERCENT.test(raw)) {
    const value = Number(raw.slice(0, -1));
    return value >= 10 && value <= 100 ? raw : undefined;
  }
  if (PIXELS.test(raw)) {
    const value = Number(raw);
    return value >= 100 && value <= 7680 ? `${value}px` : undefined;
  }
  return undefined;
}

function parseBoundedInt(
  raw: string,
  min: number,
  max: number,
): number | undefined {
  if (!/^\d+$/.test(raw)) return undefined;
  const value = Number(raw);
  return value >= min && value <= max ? value : undefined;
}

function parseHex(raw: string): string | undefined {
  const candidate = raw.startsWith("#") ? raw : `#${raw}`;
  return HEX.test(candidate) ? candidate.toUpperCase() : undefined;
}

function parseOpacity(raw: string): number | undefined {
  if (!/^(0|1|0?\.\d{1,3})$/.test(raw)) return undefined;
  const value = Number(raw);
  return value >= 0 && value <= 1 ? value : undefined;
}

function parseAlign(raw: string): OverlayAlign | undefined {
  return raw === "left" || raw === "center" || raw === "right" ? raw : undefined;
}

/**
 * Per-page overrides from the query string. Only keys that are present *and*
 * valid come back, so an invalid parameter falls back to the backend setting
 * rather than to a hard-coded default that would contradict the control page.
 */
export function parseOverlayOverrides(
  params: URLSearchParams,
): Partial<OverlayStyle> {
  const overrides: Partial<OverlayStyle> = {};
  const take = <K extends keyof OverlayStyle>(
    name: string,
    parse: (raw: string) => OverlayStyle[K] | undefined,
    key: K,
  ): void => {
    const raw = params.get(name);
    if (raw === null) return;
    const value = parse(raw);
    if (value !== undefined) overrides[key] = value;
  };

  take("width", parseWidth, "width");
  take("lines", (raw) => parseBoundedInt(raw, 1, 10), "lines");
  take("size", (raw) => parseBoundedInt(raw, 12, 200), "size");
  take("font", (raw) => FONT_STACKS[raw], "font");
  take("color", parseHex, "color");
  take("bg", parseHex, "bg");
  take("opacity", parseOpacity, "opacity");
  take("align", parseAlign, "align");
  take("outline", (raw) => parseBoundedInt(raw, 0, 8), "outlineWidth");
  take("outlinecolor", parseHex, "outlineColor");
  take("padding", (raw) => parseBoundedInt(raw, 0, 64), "padding");
  take("radius", (raw) => parseBoundedInt(raw, 0, 48), "radius");
  return overrides;
}

/** Kept for callers that want the defaults plus whatever the URL specifies. */
export function parseOverlayStyle(params: URLSearchParams): OverlayStyle {
  return { ...DEFAULT_OVERLAY_STYLE, ...parseOverlayOverrides(params) };
}

export function hexToRgba(hex: string, opacity: number): string {
  const red = Number.parseInt(hex.slice(1, 3), 16);
  const green = Number.parseInt(hex.slice(3, 5), 16);
  const blue = Number.parseInt(hex.slice(5, 7), 16);
  return `rgba(${red}, ${green}, ${blue}, ${opacity})`;
}

// A ring of offsets rather than `-webkit-text-stroke`: a stroke is centred on
// the glyph edge and eats into the letterform, which thins small CJK
// characters exactly when the outline is meant to make them readable. A
// text-shadow ring is drawn behind the text and never touches it.
const RING: ReadonlyArray<readonly [number, number]> = [
  [1, 0],
  [-1, 0],
  [0, 1],
  [0, -1],
  [0.75, 0.75],
  [0.75, -0.75],
  [-0.75, 0.75],
  [-0.75, -0.75],
];

/** The `text-shadow` value implementing the outline and the drop shadow. */
export function textShadowFor(style: OverlayStyle): string {
  const layers: string[] = [];
  if (style.outlineWidth > 0) {
    for (const [dx, dy] of RING) {
      const x = (dx * style.outlineWidth).toFixed(2);
      const y = (dy * style.outlineWidth).toFixed(2);
      layers.push(`${x}px ${y}px 0 ${style.outlineColor}`);
    }
  }
  if (style.shadow) {
    // Drawn last so it sits under the outline rather than blurring it.
    layers.push("0 2px 6px rgba(0, 0, 0, 0.85)");
  }
  return layers.length > 0 ? layers.join(", ") : "none";
}

const LINE_HEIGHT = 1.3;

/**
 * Size the box to `lineCount` lines. Line breaking itself belongs to the
 * backend formatter (Stage 3.1); the `lines` query parameter only overrides
 * how many of those lines this particular overlay shows, so two Browser
 * Inputs can display different heights of the same caption.
 */
export function toCssVariables(
  style: OverlayStyle,
  lineCount: number = style.lines,
): CSSProperties {
  return {
    "--caption-width": style.width,
    "--caption-size": `${style.size}px`,
    "--caption-font": style.font,
    "--caption-weight": style.weight,
    "--caption-color": style.color,
    "--caption-bg": hexToRgba(style.bg, style.opacity),
    "--caption-align": style.align,
    "--caption-padding": `${style.padding}px`,
    "--caption-radius": `${style.radius}px`,
    "--caption-text-shadow": textShadowFor(style),
    "--caption-line-height": `${LINE_HEIGHT}`,
    "--caption-height": `${(style.size * LINE_HEIGHT * Math.max(1, lineCount)).toFixed(2)}px`,
  } as CSSProperties;
}
