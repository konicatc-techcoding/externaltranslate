import { useEffect, useRef, useState } from "react";

import { zhTW } from "../i18n/zh-TW";

interface TranslationClockProps {
  elapsedSeconds: number;
  running: boolean;
  /** Injected in tests so the tick is deterministic. */
  now?: () => number;
}

export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  return [hours, minutes, secs]
    .map((part) => String(part).padStart(2, "0"))
    .join(":");
}

/**
 * Elapsed time of the current translation run.
 *
 * The authoritative value comes from the backend, so reloading the page or
 * opening the control page mid-run still shows the true duration. Between
 * snapshots the clock ticks locally, because the socket only pushes on change
 * and an idle run would otherwise appear frozen.
 */
export function TranslationClock({
  elapsedSeconds,
  running,
  now,
}: TranslationClockProps) {
  // Kept in a ref, never in an effect's dependency list: a clock source is a
  // fresh function on every render (including the default one), so depending
  // on it would re-run the effect forever.
  const nowRef = useRef<() => number>(now ?? (() => Date.now()));
  nowRef.current = now ?? (() => Date.now());

  const base = useRef({ elapsed: elapsedSeconds, at: nowRef.current() });
  const [, setTick] = useState(0);

  useEffect(() => {
    base.current = { elapsed: elapsedSeconds, at: nowRef.current() };
    setTick((value) => value + 1);
  }, [elapsedSeconds, running]);

  useEffect(() => {
    if (!running) {
      return;
    }
    const timer = window.setInterval(() => setTick((value) => value + 1), 250);
    return () => window.clearInterval(timer);
  }, [running]);

  const shown = running
    ? base.current.elapsed + (nowRef.current() - base.current.at) / 1000
    : elapsedSeconds;

  return (
    <output
      className="clock"
      aria-label={zhTW.clock.label}
      data-running={running ? "true" : "false"}
      aria-live="off"
    >
      {formatDuration(shown)}
    </output>
  );
}
