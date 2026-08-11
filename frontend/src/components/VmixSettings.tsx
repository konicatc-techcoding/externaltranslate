import { useEffect, useState } from "react";

import { zhTW } from "../i18n/zh-TW";
import type { VmixInputItem, VmixSettings as VmixConfig } from "../types/runtime";

interface VmixSettingsProps {
  settings: VmixConfig;
  inputs: VmixInputItem[];
  /** Caption lines currently configured, to flag a field-count mismatch. */
  maxLines: number;
  overlayUrl: string;
  notice: string | null;
  onChange: (update: Partial<VmixConfig>) => void;
  onRefresh: () => void;
  onTest: () => void;
  onClearFields: () => void;
  /** Testing while translating is refused: the next caption overwrites it. */
  running?: boolean;
}

const LOOPBACK = new Set(["127.0.0.1", "localhost", "::1"]);

/** `Line1.Text … LineN.Text`, the convention the operator can copy into vMix. */
export function generateFieldNames(lines: number): string[] {
  return Array.from({ length: lines }, (_value, index) => `Line${index + 1}.Text`);
}

export function VmixSettings({
  settings,
  inputs,
  maxLines,
  overlayUrl,
  notice,
  onChange,
  onRefresh,
  onTest,
  onClearFields,
  running = false,
}: VmixSettingsProps) {
  const [fieldText, setFieldText] = useState(settings.fields.join("\n"));
  const [copied, setCopied] = useState(false);
  // Host and port are edited locally and sent on blur. Committing per
  // keystroke means typing "192." is rejected — a host may not end in a dot —
  // and the rejected value is echoed straight back, so the character vanishes
  // as it is typed and the field can never be cleared.
  const [host, setHost] = useState(settings.host);
  const [port, setPort] = useState(String(settings.port));
  // Turning the output off while translating takes the captions off air the
  // moment it is sent, so it is asked about first. Inline rather than
  // `window.confirm`: a modal that steals focus mid-show is worse than the
  // mistake it prevents.
  const [confirmingDisable, setConfirmingDisable] = useState(false);

  useEffect(() => {
    setHost(settings.host);
    setPort(String(settings.port));
  }, [settings.host, settings.port]);

  const commitFields = (raw: string): void => {
    const fields = raw
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.length > 0);
    if (fields.length > 0) {
      onChange({ fields });
    }
  };

  const commitHost = (): void => {
    const trimmed = host.trim();
    if (trimmed === settings.host) {
      return;
    }
    if (trimmed === "") {
      setHost(settings.host); // nothing to send; put back what is in force
      return;
    }
    onChange({ host: trimmed });
  };

  const commitPort = (): void => {
    const value = Number(port);
    if (!Number.isInteger(value) || value < 1 || value > 65535) {
      setPort(String(settings.port));
      return;
    }
    if (value !== settings.port) {
      onChange({ port: value });
    }
  };

  const toggleEnabled = (checked: boolean): void => {
    // Only the off direction, and only on air: with nothing running there is
    // no caption to remove, and a prompt would just be in the way.
    if (!checked && running) {
      setConfirmingDisable(true);
      return;
    }
    onChange({ enabled: checked });
  };

  const isRemote = !LOOPBACK.has(settings.host);
  const mismatch = settings.fields.length < maxLines;

  return (
    <section className="panel" aria-labelledby="vmix-title">
      <h2 id="vmix-title">{zhTW.vmix.title}</h2>
      <p className="panel__note">{zhTW.vmix.note}</p>

      {notice !== null ? (
        <p role="status" className="panel__notice">
          {notice}
        </p>
      ) : null}

      {confirmingDisable ? (
        <div role="alertdialog" aria-label={zhTW.vmix.disableTitle} className="panel__notice">
          <p>{zhTW.vmix.disableConfirm}</p>
          <button
            type="button"
            onClick={() => {
              setConfirmingDisable(false);
              onChange({ enabled: false });
            }}
          >
            {zhTW.vmix.disableAccept}
          </button>
          <button type="button" onClick={() => setConfirmingDisable(false)}>
            {zhTW.vmix.disableCancel}
          </button>
        </div>
      ) : null}

      <div className="field-row">
        <label>
          <input
            type="checkbox"
            checked={settings.enabled}
            onChange={(event) => toggleEnabled(event.target.checked)}
          />
          {zhTW.vmix.enabled}
        </label>

        <label htmlFor="vmix-host">{zhTW.vmix.host}</label>
        <input
          id="vmix-host"
          value={host}
          onChange={(event) => setHost(event.target.value)}
          onBlur={() => commitHost()}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              commitHost();
            }
          }}
        />

        <label htmlFor="vmix-port">{zhTW.vmix.port}</label>
        <input
          id="vmix-port"
          type="number"
          min={1}
          max={65535}
          value={port}
          onChange={(event) => setPort(event.target.value)}
          onBlur={() => commitPort()}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              commitPort();
            }
          }}
        />
      </div>

      {isRemote ? (
        <p className="panel__warning">{zhTW.vmix.remoteWarning}</p>
      ) : null}

      <div className="field-row">
        <button type="button" onClick={onRefresh}>
          {zhTW.vmix.refresh}
        </button>

        <label htmlFor="vmix-input">{zhTW.vmix.input}</label>
        <select
          id="vmix-input"
          value={settings.input_guid ?? ""}
          onChange={(event) => {
            const chosen = inputs.find((item) => item.guid === event.target.value);
            // The GUID is stored; the name is only how a human recognises it.
            onChange({
              input_guid: chosen?.guid ?? null,
              input_name: chosen?.name ?? null,
            });
          }}
        >
          <option value="">—</option>
          {inputs.map((item) => (
            <option key={item.guid} value={item.guid}>
              {item.name}
            </option>
          ))}
        </select>
      </div>

      {inputs.length === 0 ? (
        <p className="panel__note">{zhTW.vmix.noInputs}</p>
      ) : null}

      <div className="field-row">
        <label htmlFor="vmix-fields">{zhTW.vmix.fields}</label>
        <textarea
          id="vmix-fields"
          rows={Math.min(6, Math.max(2, settings.fields.length))}
          value={fieldText}
          onChange={(event) => setFieldText(event.target.value)}
          onBlur={(event) => commitFields(event.target.value)}
        />
        <button
          type="button"
          onClick={() => {
            const generated = generateFieldNames(maxLines);
            setFieldText(generated.join("\n"));
            onChange({ fields: generated });
          }}
        >
          {zhTW.vmix.generate}
        </button>
      </div>
      <p className="panel__note">{zhTW.vmix.fieldsHint}</p>

      {mismatch ? (
        <p className="panel__warning">
          {zhTW.vmix.mismatch
            .replace("{lines}", String(maxLines))
            .replace("{fields}", String(settings.fields.length))}
        </p>
      ) : null}

      <div className="field-row">
        <button
          type="button"
          onClick={onTest}
          disabled={settings.input_guid === null || running}
        >
          {zhTW.vmix.test}
        </button>
        <button
          type="button"
          onClick={onClearFields}
          disabled={settings.input_guid === null || running}
        >
          {zhTW.vmix.clearFields}
        </button>
        {running ? <span>{zhTW.vmix.testBusy}</span> : null}
      </div>
      <p className="panel__note">{zhTW.vmix.testHint}</p>

      <div className="field-row">
        <label htmlFor="vmix-overlay-url">{zhTW.vmix.overlayUrl}</label>
        <input id="vmix-overlay-url" readOnly value={overlayUrl} />
        <button
          type="button"
          onClick={() => {
            void navigator.clipboard?.writeText(overlayUrl).then(() => setCopied(true));
          }}
        >
          {copied ? zhTW.vmix.copied : zhTW.vmix.copy}
        </button>
      </div>
    </section>
  );
}
