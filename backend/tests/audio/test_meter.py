from __future__ import annotations

import numpy as np
import pytest

from backend.app.audio.meter import calculate_meter


def test_calculate_meter_reports_rms_peak_and_dbfs() -> None:
    reading = calculate_meter(np.array([0.5, -0.5], dtype=np.float32))

    assert reading.rms == pytest.approx(0.5)
    assert reading.peak == pytest.approx(0.5)
    assert reading.rms_dbfs == pytest.approx(-6.0206, abs=0.001)
    assert reading.peak_dbfs == pytest.approx(-6.0206, abs=0.001)
    assert reading.clipping is False


def test_calculate_meter_handles_silence_without_negative_infinity() -> None:
    reading = calculate_meter(np.zeros(1600, dtype=np.float32))

    assert reading.rms == 0.0
    assert reading.peak == 0.0
    assert reading.rms_dbfs == -120.0
    assert reading.peak_dbfs == -120.0


def test_calculate_meter_marks_full_scale_as_clipping() -> None:
    reading = calculate_meter(np.array([0.0, 1.0], dtype=np.float32))

    assert reading.clipping is True
