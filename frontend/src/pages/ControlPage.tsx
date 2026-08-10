import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "../api/client";
import { connectCaptionSocket, type SocketState } from "../api/websocket";
import { ApiKeyField } from "../components/ApiKeyField";
import { AudioMeter } from "../components/AudioMeter";
import { AudioSourceSelector } from "../components/AudioSourceSelector";
import { CaptionLayoutSettings } from "../components/CaptionLayoutSettings";
import { CaptionPresets } from "../components/CaptionPresets";
import { CaptionPreview } from "../components/CaptionPreview";
import { CaptionStyleSettings } from "../components/CaptionStyleSettings";
import { ComponentStatusList } from "../components/ComponentStatusList";
import { PrerequisitePanel } from "../components/PrerequisitePanel";
import { TranslationClock } from "../components/TranslationClock";
import { zhTW } from "../i18n/zh-TW";
import {
  IDLE_RUNTIME_STATUS,
  type AppSettings,
  type DeviceItem,
  type LoopbackEndpointItem,
  type CaptionPreset,
  type PrerequisiteItem,
  type RuntimeStatus,
  type SourceKind,
} from "../types/runtime";

export type UiState =
  | "idle"
  | "checking"
  | "ready"
  | "listening"
  | "translating"
  | "stopping"
  | "error";

export function deriveUiState(input: {
  loading: boolean;
  stopping: boolean;
  error: string | null;
  configured: boolean;
  status: RuntimeStatus;
}): UiState {
  if (input.error !== null) return "error";
  if (input.stopping) return "stopping";
  if (input.loading) return "checking";
  if (input.status.running) {
    return input.status.caption.status === "idle" ? "listening" : "translating";
  }
  return input.configured ? "ready" : "idle";
}

export function ControlPage() {
  const [prerequisites, setPrerequisites] = useState<PrerequisiteItem[]>([]);
  const [devices, setDevices] = useState<DeviceItem[]>([]);
  const [endpoints, setEndpoints] = useState<LoopbackEndpointItem[]>([]);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [configured, setConfigured] = useState(false);
  const [status, setStatus] = useState<RuntimeStatus>(IDLE_RUNTIME_STATUS);
  const [socketState, setSocketState] = useState<SocketState>("connecting");
  const [loading, setLoading] = useState(true);
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [presets, setPresets] = useState<CaptionPreset[]>([]);

  const report = useCallback((caught: unknown) => {
    setError(caught instanceof ApiError ? caught.message : zhTW.errors.generic);
  }, []);

  const loadCatalog = useCallback(async () => {
    setLoading(true);
    try {
      const [prereq, deviceList, endpointList, currentSettings, credential, presetList] =
        await Promise.all([
          api.prerequisites(),
          api.devices().catch(() => ({ devices: [] as DeviceItem[] })),
          api
            .loopbackEndpoints()
            .catch(() => ({ endpoints: [] as LoopbackEndpointItem[] })),
          api.settings(),
          api.credentialState(),
          api.presets().catch(() => ({ presets: [] as CaptionPreset[] })),
        ]);
      setPrerequisites(prereq.results);
      setDevices(deviceList.devices);
      setEndpoints(endpointList.endpoints);
      setSettings(currentSettings);
      setConfigured(credential.configured);
      setPresets(presetList.presets);
      setError(null);
    } catch (caught) {
      report(caught);
    } finally {
      setLoading(false);
    }
  }, [report]);

  useEffect(() => {
    void loadCatalog();
  }, [loadCatalog]);

  useEffect(() => {
    const socket = connectCaptionSocket({
      onSnapshot: setStatus,
      onState: setSocketState,
    });
    return () => socket.close();
  }, []);

  const uiState = deriveUiState({ loading, stopping, error, configured, status });
  const stale = socketState === "stale";

  const submitKey = async (apiKey: string): Promise<void> => {
    try {
      const state = await api.submitCredential(apiKey);
      setConfigured(state.configured);
      setTestResult(null);
      setError(null);
    } catch (caught) {
      report(caught);
    }
  };

  const changeAudio = async (update: {
    source_kind: SourceKind;
    device_index?: number | null;
    loopback_endpoint_index?: number | null;
    channel?: number | null;
  }): Promise<void> => {
    try {
      setSettings(await api.updateSettings(update));
      setError(null);
    } catch (caught) {
      report(caught);
    }
  };

  return (
    <main className="app-shell">
      <header className="app-header">
        <h1>{zhTW.productName}</h1>
        <p>{zhTW.productDescription}</p>
        <output className="status-badge" aria-live="polite" data-ui-state={uiState}>
          {zhTW.ui[uiState]}
        </output>
      </header>

      {error !== null ? (
        <p role="alert" className="panel__error">
          {error}
        </p>
      ) : null}

      <PrerequisitePanel
        items={prerequisites}
        busy={loading}
        onRefresh={() => void loadCatalog()}
      />

      <ApiKeyField
        configured={configured}
        busy={status.running}
        testResult={testResult}
        onSubmit={(key) => void submitKey(key)}
        onTest={() => {
          void api
            .testCredential()
            .then((result) => setTestResult(result.message))
            .catch(report);
        }}
        onClear={() => {
          void api
            .clearCredential()
            .then((state) => {
              setConfigured(state.configured);
              setTestResult(null);
            })
            .catch(report);
        }}
      />

      {status.audio_notice !== null ? (
        <p role="status" className="panel__notice">
          {status.audio_notice}
        </p>
      ) : null}

      {settings !== null ? (
        <AudioSourceSelector
          settings={settings}
          devices={devices}
          endpoints={endpoints}
          disabled={status.running}
          onRefresh={() => void loadCatalog()}
          onChange={(update) => void changeAudio(update)}
        />
      ) : null}

      <section className="panel">
        <div className="field-row">
          <button
            type="button"
            onClick={() => {
              void api
                .start()
                .then(() => setError(null))
                .catch(report);
            }}
            disabled={!configured || status.running || stopping}
          >
            {zhTW.controls.start}
          </button>
          <button
            type="button"
            onClick={() => {
              setStopping(true);
              void api
                .stop()
                .catch(report)
                .finally(() => setStopping(false));
            }}
            disabled={!status.running || stopping}
          >
            {zhTW.controls.stop}
          </button>
          <TranslationClock
            elapsedSeconds={status.elapsed_seconds}
            running={status.running}
          />
          {!configured ? <span>{zhTW.controls.startBlocked}</span> : null}
        </div>
      </section>

      <CaptionLayoutSettings
        layout={status.layout}
        onChange={(charsPerLine, maxLines) => {
          void api
            .updateCaptionLayout(charsPerLine, maxLines)
            .then(() => setError(null))
            .catch(report);
        }}
      />

      <CaptionStyleSettings
        style={status.style}
        onChange={(style) => {
          void api
            .updateCaptionStyle(style)
            .then(() => setError(null))
            .catch(report);
        }}
      />

      <CaptionPresets
        presets={presets}
        onSave={(name) => {
          void api
            .savePreset(name)
            .then((result) => {
              setPresets(result.presets);
              setError(null);
            })
            .catch(report);
        }}
        onApply={(name) => {
          void api.applyPreset(name).then(() => setError(null)).catch(report);
        }}
        onDelete={(name) => {
          void api
            .deletePreset(name)
            .then((result) => setPresets(result.presets))
            .catch(report);
        }}
      />

      <AudioMeter meter={status.meter} />
      <ComponentStatusList components={status.components} stale={stale} />

      <section className="panel" aria-labelledby="caption-title">
        <div className="panel__header">
          <h2 id="caption-title">{zhTW.caption.title}</h2>
          <div className="field-row">
            <button
              type="button"
              className="button--danger"
              title={zhTW.caption.clearHint}
              onClick={() => {
                void api
                  .clearCaptions()
                  .then(() => setError(null))
                  .catch(report);
              }}
            >
              {zhTW.caption.clear}
            </button>
            <a href="/overlay" target="_blank" rel="noreferrer">
              {zhTW.caption.overlayLink}
            </a>
          </div>
        </div>
        <CaptionPreview
          caption={status.caption}
          stale={stale}
          maxLines={status.layout.max_lines}
          scroll={status.style.scroll}
          scrollMs={status.style.scroll_ms}
        />
      </section>
    </main>
  );
}
