import { useEffect, useState } from "react";

import { zhTW } from "../i18n/zh-TW";
import type { CaptionLayout } from "../types/runtime";

interface CaptionLayoutSettingsProps {
  layout: CaptionLayout;
  onChange: (chars_per_line: number, max_lines: number) => void;
}

export const CHARS_PER_LINE_RANGE = [4, 60] as const;
export const MAX_LINES_RANGE = [1, 10] as const;

/**
 * Caption layout is adjustable while translating: taking captions off air to
 * change how many characters fit on a line would be unusable during a live
 * event. The backend re-flows the current caption immediately.
 */
export function CaptionLayoutSettings({
  layout,
  onChange,
}: CaptionLayoutSettingsProps) {
  const [chars, setChars] = useState(String(layout.chars_per_line));
  const [lines, setLines] = useState(String(layout.max_lines));

  // The server is the source of truth: adopt whatever it reports, including
  // a value it corrected or another client changed.
  useEffect(() => {
    setChars(String(layout.chars_per_line));
    setLines(String(layout.max_lines));
  }, [layout.chars_per_line, layout.max_lines]);

  const commit = (nextChars: string, nextLines: string): void => {
    const parsedChars = Number(nextChars);
    const parsedLines = Number(nextLines);
    if (!Number.isInteger(parsedChars) || !Number.isInteger(parsedLines)) {
      return;
    }
    if (
      parsedChars < CHARS_PER_LINE_RANGE[0] ||
      parsedChars > CHARS_PER_LINE_RANGE[1] ||
      parsedLines < MAX_LINES_RANGE[0] ||
      parsedLines > MAX_LINES_RANGE[1]
    ) {
      return;
    }
    onChange(parsedChars, parsedLines);
  };

  return (
    <section className="panel" aria-labelledby="caption-layout-title">
      <h2 id="caption-layout-title">{zhTW.captionLayout.title}</h2>
      <p className="panel__note">{zhTW.captionLayout.note}</p>
      <div className="field-row">
        <label htmlFor="chars-per-line">{zhTW.captionLayout.charsPerLine}</label>
        <input
          id="chars-per-line"
          type="number"
          inputMode="numeric"
          min={CHARS_PER_LINE_RANGE[0]}
          max={CHARS_PER_LINE_RANGE[1]}
          value={chars}
          onChange={(event) => {
            setChars(event.target.value);
            commit(event.target.value, lines);
          }}
        />
        <label htmlFor="max-lines">{zhTW.captionLayout.maxLines}</label>
        <input
          id="max-lines"
          type="number"
          inputMode="numeric"
          min={MAX_LINES_RANGE[0]}
          max={MAX_LINES_RANGE[1]}
          value={lines}
          onChange={(event) => {
            setLines(event.target.value);
            commit(chars, event.target.value);
          }}
        />
      </div>
    </section>
  );
}
