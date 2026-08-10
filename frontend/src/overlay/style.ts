import type { CSSProperties } from "react";

export type OverlayAlign = "left" | "center" | "right";

export interface OverlayStyle {
  width: string;
  lines: number;
  size: number;
  font: string;
  color: string;
  bg: string;
  opacity: number;
  align: OverlayAlign;
}

/**
 * Font families are a closed whitelist. A query parameter interpolated into
 * a CSS font stack would otherwise be an injection point, and a caption
 * overlay is pasted into vMix and OBS from URLs users copy around.
 */
export const FONT_STACKS: Record<string, string> = {
  sans: '"Noto Sans TC", "Microsoft JhengHei", system-ui, sans-serif',
  serif: '"Noto Serif TC", "Microsoft JhengHei", Georgia, serif',
  mono: '"Noto Sans Mono CJK TC", Consolas, monospace',
};

export const DEFAULT_OVERLAY_STYLE: OverlayStyle = {
  width: "90%",
  lines: 2,
  size: 48,
  font: FONT_STACKS.sans,
  color: "#FFFFFF",
  bg: "#000000",
  opacity: 0.5,
  // Left by default: captions accumulate fragment by fragment, and centred
  // text reflows on every update so each word shifts sideways as the line
  // grows. Anchoring at the left edge keeps already-read text still.
  align: "left",
};

const HEX = /^#[0-9a-fA-F]{6}$/;
const PERCENT = /^\d{1,3}%$/;
const PIXELS = /^\d{2,5}$/;

function parseWidth(raw: string | null): string {
  if (raw === null) return DEFAULT_OVERLAY_STYLE.width;
  if (PERCENT.test(raw)) {
    const value = Number(raw.slice(0, -1));
    return value >= 10 && value <= 100 ? raw : DEFAULT_OVERLAY_STYLE.width;
  }
  if (PIXELS.test(raw)) {
    const value = Number(raw);
    return value >= 100 && value <= 7680 ? `${value}px` : DEFAULT_OVERLAY_STYLE.width;
  }
  return DEFAULT_OVERLAY_STYLE.width;
}

function parseBoundedInt(
  raw: string | null,
  min: number,
  max: number,
  fallback: number,
): number {
  if (raw === null || !/^\d+$/.test(raw)) return fallback;
  const value = Number(raw);
  return value >= min && value <= max ? value : fallback;
}

function parseHex(raw: string | null, fallback: string): string {
  if (raw === null) return fallback;
  const candidate = raw.startsWith("#") ? raw : `#${raw}`;
  return HEX.test(candidate) ? candidate.toUpperCase() : fallback;
}

function parseOpacity(raw: string | null): number {
  if (raw === null || !/^(0|1|0?\.\d{1,3})$/.test(raw)) {
    return DEFAULT_OVERLAY_STYLE.opacity;
  }
  const value = Number(raw);
  return value >= 0 && value <= 1 ? value : DEFAULT_OVERLAY_STYLE.opacity;
}

function parseAlign(raw: string | null): OverlayAlign {
  return raw === "left" || raw === "center" || raw === "right"
    ? raw
    : DEFAULT_OVERLAY_STYLE.align;
}

/** Every invalid or missing parameter falls back to the default. */
export function parseOverlayStyle(params: URLSearchParams): OverlayStyle {
  const fontKey = params.get("font");
  return {
    width: parseWidth(params.get("width")),
    lines: parseBoundedInt(params.get("lines"), 1, 10, DEFAULT_OVERLAY_STYLE.lines),
    size: parseBoundedInt(params.get("size"), 12, 200, DEFAULT_OVERLAY_STYLE.size),
    font:
      fontKey !== null && fontKey in FONT_STACKS
        ? FONT_STACKS[fontKey]
        : DEFAULT_OVERLAY_STYLE.font,
    color: parseHex(params.get("color"), DEFAULT_OVERLAY_STYLE.color),
    bg: parseHex(params.get("bg"), DEFAULT_OVERLAY_STYLE.bg),
    opacity: parseOpacity(params.get("opacity")),
    align: parseAlign(params.get("align")),
  };
}

export function hexToRgba(hex: string, opacity: number): string {
  const red = Number.parseInt(hex.slice(1, 3), 16);
  const green = Number.parseInt(hex.slice(3, 5), 16);
  const blue = Number.parseInt(hex.slice(5, 7), 16);
  return `rgba(${red}, ${green}, ${blue}, ${opacity})`;
}

const LINE_HEIGHT = 1.3;

/**
 * The caption box height is exactly `lines`, and the content sticks to the
 * bottom — that is what makes "lines" behave as a sliding window over the
 * accumulating caption instead of a hard character budget.
 */
export function toCssVariables(style: OverlayStyle): CSSProperties {
  return {
    "--caption-width": style.width,
    "--caption-size": `${style.size}px`,
    "--caption-font": style.font,
    "--caption-color": style.color,
    "--caption-bg": hexToRgba(style.bg, style.opacity),
    "--caption-align": style.align,
    "--caption-line-height": `${LINE_HEIGHT}`,
    "--caption-height": `${(style.size * LINE_HEIGHT * style.lines).toFixed(2)}px`,
  } as CSSProperties;
}
