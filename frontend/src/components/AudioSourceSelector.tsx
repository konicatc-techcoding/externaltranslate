import { zhTW } from "../i18n/zh-TW";
import type {
  AppSettings,
  DeviceItem,
  LoopbackEndpointItem,
  SourceKind,
} from "../types/runtime";

interface AudioSourceSelectorProps {
  settings: AppSettings;
  devices: DeviceItem[];
  endpoints: LoopbackEndpointItem[];
  disabled?: boolean;
  onRefresh: () => void;
  onChange: (update: {
    source_kind: SourceKind;
    device_index?: number | null;
    loopback_endpoint_index?: number | null;
    channel?: number | null;
  }) => void;
}

/**
 * The two sources are mutually exclusive in the UI as well as the backend:
 * picking one clears the other's selection in the same request.
 */
export function AudioSourceSelector({
  settings,
  devices,
  endpoints,
  disabled = false,
  onRefresh,
  onChange,
}: AudioSourceSelectorProps) {
  const isInput = settings.source_kind === "input_device";

  return (
    <section className="panel" aria-labelledby="audio-title">
      <div className="panel__header">
        <h2 id="audio-title">{zhTW.audio.title}</h2>
        <button type="button" onClick={onRefresh} disabled={disabled}>
          {zhTW.audio.refresh}
        </button>
      </div>
      <p className="panel__note">{zhTW.audio.indexWarning}</p>

      <div className="field-row">
        <label>
          <input
            type="radio"
            name="source-kind"
            checked={isInput}
            disabled={disabled}
            onChange={() =>
              onChange({
                source_kind: "input_device",
                device_index: devices[0]?.index ?? null,
                channel: settings.channel,
              })
            }
          />
          {zhTW.audio.inputDevice}
        </label>
        <label>
          <input
            type="radio"
            name="source-kind"
            checked={!isInput}
            disabled={disabled}
            onChange={() =>
              onChange({
                source_kind: "wasapi_loopback",
                loopback_endpoint_index: null,
              })
            }
          />
          {zhTW.audio.loopback}
        </label>
      </div>

      {isInput ? (
        <div className="field-row">
          <label htmlFor="device-index">{zhTW.audio.deviceSelect}</label>
          <select
            id="device-index"
            value={settings.device_index ?? ""}
            disabled={disabled || devices.length === 0}
            onChange={(event) =>
              onChange({
                source_kind: "input_device",
                device_index: Number(event.target.value),
                channel: settings.channel,
              })
            }
          >
            {devices.map((device) => (
              <option key={device.index} value={device.index}>
                {`${device.index}: ${device.name}`}
              </option>
            ))}
          </select>
          <label htmlFor="channel">{zhTW.audio.channel}</label>
          <select
            id="channel"
            value={settings.channel}
            disabled={disabled}
            onChange={(event) =>
              onChange({
                source_kind: "input_device",
                device_index: settings.device_index,
                channel: Number(event.target.value),
              })
            }
          >
            {[1, 2].map((channel) => (
              <option key={channel} value={channel}>
                {channel}
              </option>
            ))}
          </select>
          {devices.length === 0 ? <span>{zhTW.audio.noDevices}</span> : null}
        </div>
      ) : (
        <div className="field-row">
          <label htmlFor="endpoint-index">{zhTW.audio.endpointSelect}</label>
          <select
            id="endpoint-index"
            value={settings.loopback_endpoint_index ?? ""}
            disabled={disabled}
            onChange={(event) =>
              onChange({
                source_kind: "wasapi_loopback",
                loopback_endpoint_index:
                  event.target.value === "" ? null : Number(event.target.value),
              })
            }
          >
            <option value="">{zhTW.audio.useDefaultOutput}</option>
            {endpoints.map((endpoint) => (
              <option key={endpoint.index} value={endpoint.index}>
                {`${endpoint.index}: ${endpoint.name}${
                  endpoint.is_default ? `（${zhTW.audio.defaultOutput}）` : ""
                }`}
              </option>
            ))}
          </select>
          {endpoints.length === 0 ? <span>{zhTW.audio.noEndpoints}</span> : null}
        </div>
      )}
    </section>
  );
}
