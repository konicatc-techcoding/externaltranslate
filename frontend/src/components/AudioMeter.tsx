import { zhTW } from "../i18n/zh-TW";
import type { MeterPayload } from "../types/runtime";

interface AudioMeterProps {
  meter: MeterPayload | null;
}

const FLOOR_DBFS = -60;

function toPercent(dbfs: number): number {
  if (!Number.isFinite(dbfs)) {
    return 0;
  }
  const clamped = Math.max(FLOOR_DBFS, Math.min(0, dbfs));
  return Math.round(((clamped - FLOOR_DBFS) / -FLOOR_DBFS) * 100);
}

export function AudioMeter({ meter }: AudioMeterProps) {
  return (
    <section className="panel" aria-labelledby="meter-title">
      <h2 id="meter-title">{zhTW.meter.title}</h2>
      {meter === null ? (
        <p>{zhTW.meter.noSignal}</p>
      ) : (
        <div className="meter" data-clipping={meter.clipping ? "true" : "false"}>
          <div className="meter__row">
            <span>{zhTW.meter.rms}</span>
            <progress max={100} value={toPercent(meter.rms_dbfs)} />
            <span>{`${meter.rms_dbfs.toFixed(1)} dBFS`}</span>
          </div>
          <div className="meter__row">
            <span>{zhTW.meter.peak}</span>
            <progress max={100} value={toPercent(meter.peak_dbfs)} />
            <span>{`${meter.peak_dbfs.toFixed(1)} dBFS`}</span>
          </div>
          {meter.clipping ? <p className="meter__clip">{zhTW.meter.clipping}</p> : null}
        </div>
      )}
    </section>
  );
}
