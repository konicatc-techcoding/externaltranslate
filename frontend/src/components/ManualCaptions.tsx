import { useEffect, useState } from "react";

import { zhTW } from "../i18n/zh-TW";

interface ManualCaptionsProps {
  slots: string[];
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
  slots,
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

  // The server is the source of truth, as everywhere else on this page.
  useEffect(() => {
    setDrafts(slots);
  }, [slots]);

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
        <button
          type="button"
          className="button-onair"
          disabled={busy || chosen.trim() === ""}
          onClick={() => {
            // Saved as it goes out: sending is the clearest signal that this
            // wording is the one worth keeping.
            onSlotsChange(drafts);
            onSend(chosen);
          }}
        >
          {zhTW.manual.send}
        </button>
        <button type="button" disabled={busy} onClick={onClear}>
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
