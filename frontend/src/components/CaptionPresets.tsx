import { useState } from "react";

import { zhTW } from "../i18n/zh-TW";
import type { CaptionPreset } from "../types/runtime";

interface CaptionPresetsProps {
  presets: CaptionPreset[];
  onSave: (name: string) => void;
  onApply: (name: string) => void;
  onDelete: (name: string) => void;
}

/**
 * Named caption formats. Saving captures whatever is currently in force, so
 * the operator tunes the caption once and stores the result rather than
 * re-entering numbers before each show.
 */
export function CaptionPresets({
  presets,
  onSave,
  onApply,
  onDelete,
}: CaptionPresetsProps) {
  const [name, setName] = useState("");

  const save = (): void => {
    const candidate = name.trim();
    if (!candidate) {
      return;
    }
    onSave(candidate);
    setName("");
  };

  return (
    <section className="panel" aria-labelledby="presets-title">
      <h2 id="presets-title">{zhTW.presets.title}</h2>
      <p className="panel__note">{zhTW.presets.note}</p>

      <div className="field-row">
        <input
          type="text"
          aria-label={zhTW.presets.namePlaceholder}
          placeholder={zhTW.presets.namePlaceholder}
          maxLength={60}
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <button type="button" onClick={save} disabled={!name.trim()}>
          {zhTW.presets.save}
        </button>
      </div>

      {presets.length === 0 ? (
        <p>{zhTW.presets.empty}</p>
      ) : (
        <ul className="preset-list">
          {presets.map((preset) => (
            <li key={preset.name}>
              <span className="preset-list__name">{preset.name}</span>
              <span className="preset-list__detail">
                {`${preset.chars_per_line}字 × ${preset.max_lines}行 · ${preset.size}px · ${preset.color}`}
              </span>
              <button type="button" onClick={() => onApply(preset.name)}>
                {zhTW.presets.apply}
              </button>
              <button
                type="button"
                className="button--danger"
                onClick={() => onDelete(preset.name)}
              >
                {zhTW.presets.remove}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
