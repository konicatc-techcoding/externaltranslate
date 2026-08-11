import { useEffect, useState } from "react";

import { zhTW } from "../i18n/zh-TW";
import type { CaptionLayout } from "../types/runtime";

interface CaptionLayoutSettingsProps {
  layout: CaptionLayout;
  onChange: (layout: CaptionLayout) => void;
}

export const CHARS_PER_LINE_RANGE = [4, 60] as const;
export const MAX_LINES_RANGE = [1, 10] as const;
/** 0 is "never"; anything between 0 and the floor would cut sentences apart. */
export const IDLE_RESET_MS_RANGE = [500, 30000] as const;

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
  const [idle, setIdle] = useState(String(layout.idle_reset_ms));

  // The server is the source of truth: adopt whatever it reports, including
  // a value it corrected or another client changed.
  useEffect(() => {
    setChars(String(layout.chars_per_line));
    setLines(String(layout.max_lines));
    setIdle(String(layout.idle_reset_ms));
  }, [layout.chars_per_line, layout.max_lines, layout.idle_reset_ms]);

  const commit = (
    nextChars: string,
    nextLines: string,
    sentenceBreaks: boolean = layout.sentence_breaks,
    nextIdle: string = idle,
  ): void => {
    const parsedChars = Number(nextChars);
    const parsedLines = Number(nextLines);
    const parsedIdle = Number(nextIdle);
    if (
      !Number.isInteger(parsedChars) ||
      !Number.isInteger(parsedLines) ||
      !Number.isInteger(parsedIdle)
    ) {
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
    // 0 is off; between 0 and the floor the server refuses, so do not send it
    // and leave the field as typed rather than snapping it to something else.
    if (
      parsedIdle !== 0 &&
      (parsedIdle < IDLE_RESET_MS_RANGE[0] || parsedIdle > IDLE_RESET_MS_RANGE[1])
    ) {
      return;
    }
    onChange({
      chars_per_line: parsedChars,
      max_lines: parsedLines,
      sentence_breaks: sentenceBreaks,
      idle_reset_ms: parsedIdle,
    });
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

      <div className="field-row">
        <label>
          <input
            type="checkbox"
            checked={layout.sentence_breaks}
            onChange={(event) => commit(chars, lines, event.target.checked)}
          />
          {zhTW.captionLayout.sentenceBreaks}
        </label>
      </div>
      <p className="panel__note">{zhTW.captionLayout.sentenceBreaksHint}</p>

      <div className="field-row">
        <label htmlFor="idle-reset-ms">{zhTW.captionLayout.idleReset}</label>
        <input
          id="idle-reset-ms"
          type="number"
          inputMode="numeric"
          min={0}
          max={IDLE_RESET_MS_RANGE[1]}
          step={500}
          value={idle}
          onChange={(event) => {
            setIdle(event.target.value);
            commit(chars, lines, layout.sentence_breaks, event.target.value);
          }}
        />
        {layout.idle_reset_ms === 0 ? (
          <span className="panel__note">{zhTW.captionLayout.idleResetOff}</span>
        ) : null}
      </div>
      <p className="panel__note">{zhTW.captionLayout.idleResetHint}</p>
    </section>
  );
}
