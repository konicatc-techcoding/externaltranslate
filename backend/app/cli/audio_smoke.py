from __future__ import annotations

import argparse
import contextlib
import io
import json
import time
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any, BinaryIO

from backend.app.audio.capture import create_input_device_source
from backend.app.audio.devices import AudioDeviceError
from backend.app.audio.sources.base import AudioSource
from backend.app.audio.sources.input_device import AudioCaptureError


def run_smoke_capture(
    source: AudioSource,
    *,
    duration_seconds: float,
    output_path: Path | None,
    monotonic: Callable[[], float] = time.monotonic,
    capture_started: Callable[[], None] | None = None,
) -> dict[str, Any]:
    if duration_seconds <= 0:
        raise ValueError("duration_seconds 必須大於 0。")

    chunk_count = 0
    pcm_bytes = 0
    started = False
    if output_path is None:
        recording_file: BinaryIO = io.BytesIO()
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        recording_file = output_path.open("w+b")

    try:
        with wave.open(recording_file, "wb") as recording:
            recording.setnchannels(1)
            recording.setsampwidth(2)
            recording.setframerate(16000)
            try:
                source.start()
                started = True
                if capture_started is not None:
                    capture_started()
                deadline = monotonic() + duration_seconds
                while monotonic() < deadline:
                    try:
                        chunk = source.get_pcm_chunk(timeout=0.25)
                    except TimeoutError:
                        continue
                    if len(chunk) != 3200:
                        raise AudioCaptureError(
                            "收到的 PCM chunk 不是 100 ms／16 kHz／mono PCM16"
                            "（應為 3200 bytes）。"
                        )
                    recording.writeframesraw(chunk)
                    chunk_count += 1
                    pcm_bytes += len(chunk)
            finally:
                if started:
                    source.stop()

            while True:
                try:
                    chunk = source.get_pcm_chunk(timeout=0.001)
                except TimeoutError:
                    break
                if len(chunk) != 3200:
                    raise AudioCaptureError(
                        "收到的 PCM chunk 不是 100 ms／16 kHz／mono PCM16（應為 3200 bytes）。"
                    )
                recording.writeframesraw(chunk)
                chunk_count += 1
                pcm_bytes += len(chunk)

        meter = source.latest_meter
        stats = source.stats
        if chunk_count == 0 or pcm_bytes == 0:
            raise AudioCaptureError(
                "smoke test 未收到任何 PCM frame；不得將裝置擷取判定為成功。"
            )

        recording_file.seek(0)
        with wave.open(recording_file, "rb") as recording:
            wave_validation = {
                "channels": recording.getnchannels(),
                "sample_width_bytes": recording.getsampwidth(),
                "sample_rate": recording.getframerate(),
                "frames": recording.getnframes(),
            }
    finally:
        recording_file.close()

    expected_frames = pcm_bytes // 2
    if wave_validation != {
        "channels": 1,
        "sample_width_bytes": 2,
        "sample_rate": 16000,
        "frames": expected_frames,
    }:
        raise AudioCaptureError("WAV header 或 PCM byte count 驗證失敗。")

    try:
        source.start()
    except Exception:
        with contextlib.suppress(Exception):
            source.stop()
        raise
    try:
        if not source.active:
            raise AudioCaptureError("音訊來源重新啟動後未進入 active 狀態。")
        try:
            restart_chunk = source.get_pcm_chunk(timeout=2.0)
        except TimeoutError as exc:
            raise AudioCaptureError(
                "音訊來源重新啟動後未收到 PCM，restart不得判定為成功。"
            ) from exc
        if len(restart_chunk) != 3200:
            raise AudioCaptureError(
                "音訊來源重新啟動後收到的 PCM chunk不是3,200 bytes。"
            )
    finally:
        source.stop()

    return {
        "pcm_chunks": chunk_count,
        "pcm_bytes": pcm_bytes,
        "duration_seconds": duration_seconds,
        "restart_verified": True,
        "recording_persisted": output_path is not None,
        "wave": wave_validation,
        "meter": {
            "rms": meter.rms,
            "peak": meter.peak,
            "rms_dbfs": meter.rms_dbfs,
            "peak_dbfs": meter.peak_dbfs,
            "clipping": meter.clipping,
        },
        "capture_stats": {
            "callback_blocks": stats.callback_blocks,
            "callback_errors": stats.callback_errors,
            "status_events": stats.status_events,
            "processing_errors": stats.processing_errors,
            "raw_dropped": stats.raw_dropped,
            "pcm_chunks": stats.pcm_chunks,
            "pcm_dropped": stats.pcm_dropped,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ExternalTranslate Windows 音訊擷取 smoke test")
    parser.add_argument("--device-index", type=int, required=True)
    parser.add_argument("--channel", type=int, default=1)
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        source, selection = create_input_device_source(
            device_index=args.device_index,
            channel=args.channel,
        )
        report = run_smoke_capture(
            source,
            duration_seconds=args.duration,
            output_path=args.output,
        )
        result = {
            "status": "ok",
            "device": {
                "index": selection.device.index,
                "name": selection.device.name,
                "host_api": selection.device.host_api,
                "channel": selection.channel,
                "native_sample_rate": selection.native_format.sample_rate,
                "stream_channels": selection.stream_channels,
            },
            **report,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (AudioDeviceError, AudioCaptureError, ValueError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
