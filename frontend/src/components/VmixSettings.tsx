import { useState } from "react";

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
}: VmixSettingsProps) {
  const [fieldText, setFieldText] = useState(settings.fields.join("\n"));
  const [copied, setCopied] = useState(false);

  const commitFields = (raw: string): void => {
    const fields = raw
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.length > 0);
    if (fields.length > 0) {
      onChange({ fields });
    }
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

      <div className="field-row">
        <label>
          <input
            type="checkbox"
            checked={settings.enabled}
            onChange={(event) => onChange({ enabled: event.target.checked })}
          />
          {zhTW.vmix.enabled}
        </label>

        <label htmlFor="vmix-host">{zhTW.vmix.host}</label>
        <input
          id="vmix-host"
          value={settings.host}
          onChange={(event) => onChange({ host: event.target.value.trim() })}
        />

        <label htmlFor="vmix-port">{zhTW.vmix.port}</label>
        <input
          id="vmix-port"
          type="number"
          min={1}
          max={65535}
          value={settings.port}
          onChange={(event) => {
            const port = Number(event.target.value);
            if (Number.isInteger(port) && port >= 1 && port <= 65535) {
              onChange({ port });
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
        <button type="button" onClick={onTest} disabled={settings.input_guid === null}>
          {zhTW.vmix.test}
        </button>

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
