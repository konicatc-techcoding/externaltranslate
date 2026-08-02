from __future__ import annotations

import threading

import pytest

from backend.app.audio.capture import AudioSourceController, AudioSourceSwitchError
from backend.app.audio.models import CaptureStats, MeterReading


class FakeSource:
    def __init__(self, *, fail_start: bool = False) -> None:
        self._active = False
        self.fail_start = fail_start
        self.start_calls = 0
        self.stop_calls = 0

    @property
    def active(self) -> bool:
        return self._active

    @property
    def latest_meter(self) -> MeterReading:
        return MeterReading(0.0, 0.0, -120.0, -120.0, False)

    @property
    def stats(self) -> CaptureStats:
        return CaptureStats(0, 0, 0, 0, 0, 0, 0)

    def start(self) -> None:
        self.start_calls += 1
        if self.fail_start:
            raise RuntimeError("start failed")
        self._active = True

    def stop(self) -> None:
        self.stop_calls += 1
        self._active = False

    def get_pcm_chunk(self, timeout: float) -> bytes:
        del timeout
        return b""


def test_controller_prevents_two_audio_sources_from_running_together() -> None:
    controller = AudioSourceController()
    input_source = FakeSource()
    loopback_source = FakeSource()

    controller.start(input_source)

    with pytest.raises(AudioSourceSwitchError, match="已有音訊來源正在執行"):
        controller.start(loopback_source)

    assert input_source.active is True
    assert loopback_source.start_calls == 0
    controller.stop()


def test_controller_switch_stops_old_source_before_starting_new_source() -> None:
    controller = AudioSourceController()
    input_source = FakeSource()
    loopback_source = FakeSource()
    controller.start(input_source)

    controller.switch(loopback_source)

    assert input_source.stop_calls == 1
    assert input_source.active is False
    assert loopback_source.active is True
    assert controller.active_source is loopback_source
    controller.stop()


def test_controller_retains_failed_switch_target_until_cleanup_succeeds() -> None:
    controller = AudioSourceController()
    input_source = FakeSource()
    broken_loopback = FakeSource(fail_start=True)
    controller.start(input_source)

    with pytest.raises(AudioSourceSwitchError, match="無法啟動新的音訊來源"):
        controller.switch(broken_loopback)

    assert input_source.active is False
    assert controller.active_source is broken_loopback

    controller.stop()

    assert broken_loopback.stop_calls == 1
    assert controller.active_source is None


def test_controller_concurrent_starts_preserve_source_xor() -> None:
    controller = AudioSourceController()
    first_entered = threading.Event()
    release_first = threading.Event()
    second_attempted = threading.Event()
    errors: list[Exception] = []

    class BlockingSource(FakeSource):
        def start(self) -> None:
            self.start_calls += 1
            first_entered.set()
            assert release_first.wait(timeout=1.0)
            self._active = True

    first = BlockingSource()
    second = FakeSource()

    def start_first() -> None:
        controller.start(first)

    def start_second() -> None:
        second_attempted.set()
        try:
            controller.start(second)
        except Exception as exc:
            errors.append(exc)

    first_thread = threading.Thread(target=start_first)
    second_thread = threading.Thread(target=start_second)
    first_thread.start()
    assert first_entered.wait(timeout=1.0)
    second_thread.start()
    assert second_attempted.wait(timeout=1.0)

    release_first.set()
    first_thread.join(timeout=1.0)
    second_thread.join(timeout=1.0)

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert len(errors) == 1
    assert isinstance(errors[0], AudioSourceSwitchError)
    assert first.active is True
    assert second.start_calls == 0
    assert controller.active_source is first
    controller.stop()
