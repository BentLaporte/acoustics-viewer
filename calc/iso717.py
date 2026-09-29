"""Single-number ratings (ISO 717-1 airborne, ISO 717-2 impact).

The reference curves and the C / Ctr adaptation spectra below were checked
against the standard by the project owner. The unit tests only prove that the
arithmetic follows the procedure (expected values derived by hand); there is
still no end-to-end reference result from an independent program.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

BANDS = np.array([100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250,
                  1600, 2000, 2500, 3150])
I500 = 7   # index of 500 Hz

REF_AIRBORNE = np.array([33, 36, 39, 42, 45, 48, 51, 52, 53, 54, 55, 56, 56, 56, 56, 56])
REF_IMPACT = np.array([62, 62, 62, 62, 62, 62, 61, 60, 59, 58, 57, 54, 51, 48, 45, 42])

# ISO 717-1 spectra for the adaptation terms, 1/3 octave 100-3150 Hz
SPECTRUM_1_PINK = np.array([-29, -26, -23, -21, -19, -17, -15, -13, -12, -11, -10,
                            -9, -9, -9, -9, -9])
SPECTRUM_2_TRAFFIC = np.array([-20, -20, -18, -16, -15, -14, -13, -12, -11, -9, -8,
                               -9, -10, -11, -13, -15])

LIMIT_DB = 32.0     # maximum sum of unfavourable deviations for 16 bands


@dataclass
class Rating:
    value: int              # single-number rating (shifted curve at 500 Hz)
    shift: int              # shift applied to the reference curve
    unfavourable_sum: float # dB, of the final position
    curve: np.ndarray       # shifted reference curve
    deviations: np.ndarray  # unfavourable deviation per band (dB, 0 where favourable)


def _prepare(values) -> np.ndarray:
    v = np.asarray(values, float)
    if v.shape != (16,):
        raise ValueError("expected 16 values, 100 Hz ... 3150 Hz")
    if not np.all(np.isfinite(v)):
        raise ValueError("all 16 bands are required for the rating")
    return np.round(v, 1)          # the standards work with values to 0.1 dB


def rate_airborne(values) -> Rating:
    """ISO 717-1: shift the curve up in 1 dB steps to the largest position where
    the sum of deviations *below* the curve is <= 32.0 dB."""
    v = _prepare(values)
    best = None
    for shift in range(-100, 101):
        dev = np.clip((REF_AIRBORNE + shift) - v, 0, None)
        if round(dev.sum(), 6) <= LIMIT_DB:
            best = (shift, dev)
    if best is None:
        raise ValueError("no valid curve position found")
    shift, dev = best
    return Rating(int(REF_AIRBORNE[I500] + shift), shift, float(dev.sum()),
                  REF_AIRBORNE + shift, dev)


def rate_impact(values) -> Rating:
    """ISO 717-2: shift the curve to the smallest position where the sum of
    deviations *above* the curve is <= 32.0 dB."""
    v = _prepare(values)
    best = None
    for shift in range(100, -101, -1):
        dev = np.clip(v - (REF_IMPACT + shift), 0, None)
        if round(dev.sum(), 6) <= LIMIT_DB:
            best = (shift, dev)
    if best is None:
        raise ValueError("no valid curve position found")
    shift, dev = best
    return Rating(int(REF_IMPACT[I500] + shift), shift, float(dev.sum()),
                  REF_IMPACT + shift, dev)


def adaptation_term(values, spectrum, rating_value: int) -> int:
    """C_j = X_Aj - X_w with X_Aj = -10 lg sum 10^((L_ij - X_i)/10), rounded to integer."""
    x = np.round(np.asarray(values, float), 1)
    x_aj = -10 * np.log10(np.sum(10 ** ((spectrum - x) / 10)))
    return int(np.round(x_aj - rating_value))


def airborne_summary(values) -> dict:
    """DnT,w (C; Ctr) style result for 16 band values (100-3150 Hz)."""
    r = rate_airborne(values)
    return {"rating": r,
            "w": r.value,
            "C": adaptation_term(values, SPECTRUM_1_PINK, r.value),
            "Ctr": adaptation_term(values, SPECTRUM_2_TRAFFIC, r.value)}
