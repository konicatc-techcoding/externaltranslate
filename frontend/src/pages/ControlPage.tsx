import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "../api/client";
import { connectCaptionSocket, type SocketState } from "../api/websocket";
import { ApiKeyField } from "../components/ApiKeyField";
import { AudioMeter } from "../components/AudioMeter";
import { AudioSourceSelector } from "../components/AudioSourceSelector";
import { CaptionPreview } from "../components/CaptionPreview";
import { CaptionSettings, captionSummary } from "../components/CaptionSettings";
import { CollapsiblePanel } from "../components/CollapsiblePanel";
import { ComponentStatusList } from "../components/ComponentStatusList";
import { PrerequisitePanel } from "../components/PrerequisitePanel";
import { TranslationClock } from "../components/TranslationClock";
import { VmixSettings } from "../components/VmixSettings";
import { zhTW } from "../i18n/zh-TW";
import { captionStyleToOverlay } from "../overlay/style";
import {
  IDLE_RUNTIME_STATUS,
  type AppSettings,
  type DeviceItem,
  type LoopbackEndpointItem,
  type CaptionPreset,
  type PrerequisiteItem,
  type RuntimeStatus,
  type SourceKind,
  type VmixInputItem,
  type VmixSettings as VmixConfig,
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

/** What the audio panel says about itself while folded away. */
export function audioSummary(
  settings: AppSettings,
  devices: DeviceItem[],
  endpoints: LoopbackEndpointItem[],
): string {
  if (settings.source_kind === "wasapi_loopback") {
    const endpoint = endpoints.find(
      (item) => item.index === settings.loopback_endpoint_index,
    );
    return endpoint ? `系統音源・${endpoint.name}` : "系統音源・Windows 預設輸出";
  }
  const device = devices.find((item) => item.index === settings.device_index);
  return device ? `麥克風・${device.name}` : "尚未選擇裝置";
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
  const [vmixInputs, setVmixInputs] = useState<VmixInputItem[]>([]);
  // Held locally rather than read back from `settings`: two panels toggled in
  // quick succession would both compute their next set from the same stale
  // response, and the second would undo the first.
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

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
      setCollapsed(new Set(currentSettings.ui.collapsed));
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

  const changeVmix = async (update: Partial<VmixConfig>): Promise<void> => {
    try {
      setSettings(await api.updateVmixSettings(update));
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

  const togglePanel = (panel: string, open: boolean): void => {
    setCollapsed((current) => {
      const next = new Set(current);
      if (open) {
        next.delete(panel);
      } else {
        next.add(panel);
      }
      // Persisting is a convenience; the panel has already moved.
      void api.updateUiSettings([...next]).catch(report);
      return next;
    });
  };

  return (
    <main className="app-shell">
      {/* Top strip: what the operator glances at while a show runs. Compact
          on purpose — it must never push the working areas off screen. */}
      <header className="app-top">
        <div className="app-top__identity">
          <h1>{zhTW.productName}</h1>
          <p>{zhTW.productDescription}</p>
          <output className="status-badge" aria-live="polite" data-ui-state={uiState}>
            {zhTW.ui[uiState]}
          </output>
        </div>
        <div className="app-top__meter">
          <AudioMeter meter={status.meter} />
        </div>
        <div className="app-top__components">
          <ComponentStatusList components={status.components} stale={stale} />
        </div>
      </header>

      {error !== null ? (
        <p role="alert" className="panel__error app-alert">
          {error}
        </p>
      ) : null}

      <section className="app-left" aria-label={zhTW.sections.operate}>
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
          // The preview is how the operator judges an outline or a colour
          // before it goes on air, so it has to render the real style.
          style={captionStyleToOverlay(status.style)}
          maxLines={status.layout.max_lines}
          scroll={status.style.scroll}
          scrollMs={status.style.scroll_ms}
        />
      </section>

      {settings !== null ? (
        <CollapsiblePanel
          title={zhTW.vmix.title}
          summary={
            settings.vmix.enabled
              ? `${zhTW.vmix.on} → ${settings.vmix.input_name ?? zhTW.vmix.noInput}`
              : zhTW.vmix.off
          }
          open={!collapsed.has("vmix")}
          onOpenChange={(open) => togglePanel("vmix", open)}
          openOnProblem={status.vmix_notice !== null}
        >
          <VmixSettings
            settings={settings.vmix}
            inputs={vmixInputs}
            maxLines={status.layout.max_lines}
            overlayUrl={`${window.location.origin}/overlay`}
            notice={status.vmix_notice}
            onChange={(update) => void changeVmix(update)}
            onRefresh={() => {
              void api
                .vmixInputs()
                .then((result) => {
                  setVmixInputs(result.inputs);
                  setError(null);
                })
                .catch(report);
            }}
            running={status.running}
            onTest={() => {
              void api
                .testVmix(null)
                .then(() => setError(null))
                .catch(report);
            }}
            onClearFields={() => {
              void api
                .clearVmix()
                .then(() => setError(null))
                .catch(report);
            }}
          />
        </CollapsiblePanel>
      ) : null}
      </section>

      <section className="app-right" aria-label={zhTW.sections.settings}>
      <PrerequisitePanel
        items={prerequisites}
        busy={loading}
        open={!collapsed.has("prerequisites")}
        onOpenChange={(open) => togglePanel("prerequisites", open)}
        onRefresh={() => void loadCatalog()}
      />

      <CollapsiblePanel
        title={zhTW.credentials.title}
        summary={configured ? zhTW.credentials.set : zhTW.credentials.unset}
        open={!collapsed.has("credentials")}
        onOpenChange={(open) => togglePanel("credentials", open)}
      >
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
      </CollapsiblePanel>

      {status.audio_notice !== null ? (
        <p role="status" className="panel__notice">
          {status.audio_notice}
        </p>
      ) : null}

      {settings !== null ? (
        <CollapsiblePanel
          title={zhTW.audio.title}
          summary={audioSummary(settings, devices, endpoints)}
          open={!collapsed.has("audio")}
          onOpenChange={(open) => togglePanel("audio", open)}
        >
          <AudioSourceSelector
            settings={settings}
            devices={devices}
            endpoints={endpoints}
            disabled={status.running}
            onRefresh={() => void loadCatalog()}
            onChange={(update) => void changeAudio(update)}
          />
        </CollapsiblePanel>
      ) : null}

      <CollapsiblePanel
        title={zhTW.sections.caption}
        summary={captionSummary(status.layout, status.style)}
        open={!collapsed.has("caption")}
        onOpenChange={(open) => togglePanel("caption", open)}
      >
        <CaptionSettings
          layout={status.layout}
          style={status.style}
          presets={presets}
          onLayoutChange={(next) => {
            void api
              .updateCaptionLayout(next)
              .then(() => setError(null))
              .catch(report);
          }}
          onStyleChange={(style) => {
            void api
              .updateCaptionStyle(style)
              .then(() => setError(null))
              .catch(report);
          }}
          onSavePreset={(name) => {
            void api
              .savePreset(name)
              .then((result) => {
                setPresets(result.presets);
                setError(null);
              })
              .catch(report);
          }}
          onApplyPreset={(name) => {
            void api.applyPreset(name).then(() => setError(null)).catch(report);
          }}
          onDeletePreset={(name) => {
            void api
              .deletePreset(name)
              .then((result) => setPresets(result.presets))
              .catch(report);
          }}
        />
      </CollapsiblePanel>
      </section>
    </main>
  );
}
