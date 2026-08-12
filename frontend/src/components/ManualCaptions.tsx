import { useEffect, useState } from "react";

import { zhTW } from "../i18n/zh-TW";
import type { VmixInputItem } from "../types/runtime";

export const MANUAL_CHARS_PER_LINE_RANGE = [4, 60] as const;

interface ManualCaptionsProps {
  /** Titles read back from vMix; the target is chosen from these. */
  inputs: VmixInputItem[];
  /** The title chosen for manual captions, or null while none is. */
  target: string | null;
  /** The translation's title, which this one may not be. */
  translationTarget: string | null;
  onTargetChange: (input: VmixInputItem | null) => void;
  onRefreshInputs: () => void;
  slots: string[];
  /** The manual title's own width; the translation's is a separate setting. */
  charsPerLine: number;
  onCharsPerLineChange: (charsPerLine: number) => void;
  /** Saved on blur, so a prepared show survives a restart. */
  onSlotsChange: (slots: string[]) => void;
  onSend: (text: string) => void;
  onClear: () => void;
  busy?: boolean;
  /** What went out last, and whether it needed more lines than the title has. */
  lastSent?: string[] | null;
  overflowed?: boolean;
  notice?: string | null;
}

/**
 * Five prepared messages and one button that puts the chosen one on air.
 *
 * Sending replaces whatever the manual title is showing and leaves it there —
 * vMix keeps text until something changes it, and a standing message is meant
 * to stand. Nothing here touches the translation title, which keeps running.
 */
export function ManualCaptions({
  inputs,
  target,
  translationTarget,
  onTargetChange,
  onRefreshInputs,
  slots,
  charsPerLine,
  onCharsPerLineChange,
  onSlotsChange,
  onSend,
  onClear,
  busy = false,
  lastSent = null,
  overflowed = false,
  notice = null,
}: ManualCaptionsProps) {
  const [drafts, setDrafts] = useState(slots);
  const [selected, setSelected] = useState(0);
  const [width, setWidth] = useState(String(charsPerLine));

  // The server is the source of truth, as everywhere else on this page.
  useEffect(() => {
    setDrafts(slots);
  }, [slots]);

  useEffect(() => {
    setWidth(String(charsPerLine));
  }, [charsPerLine]);

  const edit = (index: number, value: string): void => {
    setDrafts((current) => current.map((text, at) => (at === index ? value : text)));
  };

  const chosen = drafts[selected] ?? "";

  return (
    <section className="panel" aria-labelledby="manual-title">
      <h2 id="manual-title">{zhTW.manual.title}</h2>
      <p className="panel__note">{zhTW.manual.note}</p>

      {notice !== null ? (
        <p role="status" className="panel__notice">
          {notice}
        </p>
      ) : null}

      <div className="field-row">
        <label htmlFor="manual-input">{zhTW.manual.target}</label>
        <select
          id="manual-input"
          value={target ?? ""}
          onChange={(event) => {
            const chosen = inputs.find((item) => item.guid === event.target.value);
            onTargetChange(chosen ?? null);
          }}
        >
          <option value="">—</option>
          {inputs
            // Offering the translation's own title would only produce a
            // rejected save; leaving it out says why by omission.
            .filter((item) => item.guid !== translationTarget)
            .map((item) => (
              <option key={item.guid} value={item.guid}>
                {`${item.number}: ${item.name}`}
              </option>
            ))}
        </select>
        <button type="button" onClick={onRefreshInputs}>
          {zhTW.manual.refreshInputs}
        </button>
      </div>

      {target === null ? (
        // Said here rather than hiding the panel: an operator looking for
        // manual captions should find them, and be told what is missing.
        <p className="panel__note">
          {inputs.length === 0 ? zhTW.manual.noInputs : zhTW.manual.noTarget}
        </p>
      ) : null}

      <ol className="manual-slots">
        {drafts.map((text, index) => (
          // Position is the identity here: these are five fixed boxes, not a
          // list that grows or reorders.
          <li key={index} className="manual-slots__row">
            <label className="manual-slots__pick">
              <input
                type="radio"
                name="manual-slot"
                checked={selected === index}
                onChange={() => setSelected(index)}
              />
              <span>{index + 1}</span>
            </label>
            <input
              type="text"
              aria-label={`${zhTW.manual.slotLabel} ${index + 1}`}
              value={text}
              maxLength={200}
              onFocus={() => setSelected(index)}
              onChange={(event) => edit(index, event.target.value)}
              onBlur={() => onSlotsChange(drafts)}
            />
          </li>
        ))}
      </ol>

      <div className="field-row">
        <label htmlFor="manual-chars-per-line">{zhTW.manual.charsPerLine}</label>
        <input
          id="manual-chars-per-line"
          type="number"
          inputMode="numeric"
          min={MANUAL_CHARS_PER_LINE_RANGE[0]}
          max={MANUAL_CHARS_PER_LINE_RANGE[1]}
          value={width}
          onChange={(event) => {
            setWidth(event.target.value);
            const parsed = Number(event.target.value);
            if (
              Number.isInteger(parsed) &&
              parsed >= MANUAL_CHARS_PER_LINE_RANGE[0] &&
              parsed <= MANUAL_CHARS_PER_LINE_RANGE[1]
            ) {
              onCharsPerLineChange(parsed);
            }
          }}
        />
      </div>
      <p className="panel__note">{zhTW.manual.charsPerLineHint}</p>

      <div className="field-row">
        <button
          type="button"
          className="button-onair"
          disabled={busy || target === null || chosen.trim() === ""}
          onClick={() => {
            // Saved as it goes out: sending is the clearest signal that this
            // wording is the one worth keeping.
            onSlotsChange(drafts);
            onSend(chosen);
          }}
        >
          {zhTW.manual.send}
        </button>
        <button type="button" disabled={busy || target === null} onClick={onClear}>
          {zhTW.manual.clear}
        </button>
      </div>

      {lastSent !== null && lastSent.length > 0 ? (
        <div className="manual-onair">
          <span className="manual-onair__tag">{zhTW.manual.onAir}</span>
          <span>{lastSent.join(" / ")}</span>
        </div>
      ) : null}

      {overflowed ? (
        <p role="alert" className="panel__error">
          {zhTW.manual.overflow}
        </p>
      ) : null}
    </section>
  );
}
