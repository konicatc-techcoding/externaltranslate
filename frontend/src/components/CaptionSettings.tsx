import { CaptionLayoutSettings } from "./CaptionLayoutSettings";
import { CaptionPresets } from "./CaptionPresets";
import { CaptionStyleSettings } from "./CaptionStyleSettings";
import { FONT_LABELS } from "../overlay/style";
import type {
  CaptionLayout,
  CaptionPreset,
  CaptionStyle,
} from "../types/runtime";

interface CaptionSettingsProps {
  layout: CaptionLayout;
  style: CaptionStyle;
  presets: CaptionPreset[];
  onLayoutChange: (layout: CaptionLayout) => void;
  onStyleChange: (style: CaptionStyle) => void;
  onSavePreset: (name: string) => void;
  onApplyPreset: (name: string) => void;
  onDeletePreset: (name: string) => void;
}

/** What the panel says about itself while folded away. */
export function captionSummary(
  layout: CaptionLayout,
  style: CaptionStyle,
): string {
  const font = FONT_LABELS[style.font] ?? style.font;
  const outline = style.outline_width > 0 ? `・描邊 ${style.outline_width}` : "";
  return `${layout.chars_per_line} 字 ${layout.max_lines} 行・${font} ${style.size}px${outline}`;
}

/**
 * Layout, appearance and presets in one panel.
 *
 * They were three cards, which cost three headings and three frames for what
 * is one job: deciding how the caption looks. The three components are
 * unchanged — only their container is.
 */
export function CaptionSettings({
  layout,
  style,
  presets,
  onLayoutChange,
  onStyleChange,
  onSavePreset,
  onApplyPreset,
  onDeletePreset,
}: CaptionSettingsProps) {
  return (
    <div className="stacked-settings">
      <CaptionLayoutSettings layout={layout} onChange={onLayoutChange} />
      <CaptionStyleSettings style={style} onChange={onStyleChange} />
      <CaptionPresets
        presets={presets}
        onSave={onSavePreset}
        onApply={onApplyPreset}
        onDelete={onDeletePreset}
      />
    </div>
  );
}
