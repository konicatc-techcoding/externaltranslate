from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt

from backend.app.audio.models import MeterReading

_DBFS_FLOOR = -120.0
_CLIPPING_THRESHOLD = 0.999


def calculate_meter(samples: npt.NDArray[np.float32]) -> MeterReading:
    """Calculate normalized full-scale meter values for a mono float frame."""

    values = np.asarray(samples, dtype=np.float32).reshape(-1)
    if values.size == 0:
        rms = 0.0
        peak = 0.0
    else:
        finite_values = np.nan_to_num(values, nan=0.0, posinf=1.0, neginf=-1.0)
        peak = float(np.max(np.abs(finite_values)))
        rms = float(np.sqrt(np.mean(np.square(finite_values, dtype=np.float64))))

    return MeterReading(
        rms=rms,
        peak=peak,
        rms_dbfs=_to_dbfs(rms),
        peak_dbfs=_to_dbfs(peak),
        clipping=peak >= _CLIPPING_THRESHOLD,
    )


def _to_dbfs(value: float) -> float:
    if value <= 0.0:
        return _DBFS_FLOOR
    return max(_DBFS_FLOOR, 20.0 * math.log10(value))
