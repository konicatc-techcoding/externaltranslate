import { useState } from "react";

import { zhTW } from "../i18n/zh-TW";

interface ApiKeyFieldProps {
  configured: boolean;
  busy?: boolean;
  testResult?: string | null;
  onSubmit: (apiKey: string) => void;
  onTest: () => void;
  onClear: () => void;
}

/**
 * Placeholder shown once a key is saved. It is a fixed string, not the key and
 * not its length, so "saved" is visible without the value ever coming back.
 */
const SAVED_MASK = "••••••••••••";

/**
 * The key lives in local component state only for as long as it takes to send
 * it, and is wiped immediately after. It is never stored, never echoed back by
 * the server, and never put in a URL.
 */
export function ApiKeyField({
  configured,
  busy = false,
  testResult = null,
  onSubmit,
  onTest,
  onClear,
}: ApiKeyFieldProps) {
  const [value, setValue] = useState("");
  const [visible, setVisible] = useState(false);

  // Once saved, the field keeps showing dots so the paste is visibly retained
  // instead of appearing to vanish. Editing resumes after 清除.
  const showSaved = configured && value === "";

  const submit = (): void => {
    const candidate = value.trim();
    if (!candidate) {
      return;
    }
    onSubmit(candidate);
    setValue("");
    setVisible(false);
  };

  return (
    <section className="panel" aria-labelledby="api-key-title">
      <h2 id="api-key-title">{zhTW.credentials.title}</h2>
      <p className="panel__note">{zhTW.credentials.notice}</p>
      <div className="field-row">
        <input
          type={visible && !showSaved ? "text" : "password"}
          value={showSaved ? SAVED_MASK : value}
          aria-label={zhTW.credentials.inputLabel}
          placeholder={zhTW.credentials.placeholder}
          autoComplete="off"
          readOnly={showSaved}
          title={showSaved ? zhTW.credentials.savedHint : undefined}
          onChange={(event) => setValue(event.target.value)}
        />
        {!showSaved ? (
          <button type="button" onClick={() => setVisible((shown) => !shown)}>
            {visible ? zhTW.credentials.hide : zhTW.credentials.show}
          </button>
        ) : null}
        <button
          type="button"
          onClick={submit}
          disabled={busy || showSaved || !value.trim()}
        >
          {zhTW.credentials.submit}
        </button>
      </div>
      <div className="field-row">
        <output aria-live="polite">
          {configured ? zhTW.credentials.configured : zhTW.credentials.notConfigured}
        </output>
        <button type="button" onClick={onTest} disabled={busy || !configured}>
          {zhTW.credentials.test}
        </button>
        <button type="button" onClick={onClear} disabled={busy || !configured}>
          {zhTW.credentials.clear}
        </button>
      </div>
      {testResult !== null ? <p aria-live="polite">{testResult}</p> : null}
    </section>
  );
}
