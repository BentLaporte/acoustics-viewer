"""Service equipment sound, ISO 10052:2021 (survey method), pure functions.

NBN S 01-400-1:2022 clause 4.4 uses the same quantities for installation noise (L_Aeq,nT for
stationary installations, L_AFmax,nT for transient ones):

  k        = 10 lg((T500 + T1000 + T2000) / (3 T0))                  3.17, 6.5
  L_XY     = 10 lg((10^(L_XY,1/10) + 10^(L_XY,2/10) + 10^(L_XY,3/10)) / 3)   3.16
  L_XY,nT  = L_XY - k                                                3.17
  reported rounded to whole dB                                       7.3

L_XY,1 is measured close to the corner, L_XY,2 and L_XY,3 in the reverberant field (6.3.4).
No correction for background noise is applied (6.2.1): a level less than 6 dB above the
background is reported as measured, with a note that it is overestimated.
"""
from __future__ import annotations

import numpy as np

from .iso16283 import T0
from .levels import energy_average

N_MEASUREMENTS = 3            # 6.3.4: one close to the corner and two in the reverberant field
BACKGROUND_MARGIN_DB = 6.0    # 6.2.1: below this the level is affected by the background
K_OCTAVES = (500, 1000, 2000)  # octave bands of the reverberation index


def reverberation_index(t500: float, t1000: float, t2000: float) -> float:
    """k = 10 lg((T500 + T1000 + T2000) / (3 T0)), octave-band reverberation times in s."""
    return float(10 * np.log10((t500 + t1000 + t2000) / (3 * T0)))


def standardized_level(levels, k: float) -> float:
    """L_XY,nT = energy average of the measured levels - k (for L_Aeq,nT and for L_AFmax,nT).

    The standard prescribes three measurements (N_MEASUREMENTS); this function takes any number
    so that other ways of measuring can still be calculated. Flagging that deviation is up to
    the caller."""
    levels = np.atleast_1d(np.asarray(levels, float))
    if levels.size == 0:
        raise ValueError("no level given")
    return float(energy_average(levels)) - k


def octave_rt(thirds) -> float:
    """Octave-band reverberation time from the three one-third-octave values inside it.

    Our choice, not the standard (ISO 10052 measures T in octave bands): the arithmetic mean.
    T is a time, not a level, so the energy sum used for levels does not apply; the arithmetic
    mean is also how ISO 10052 3.17 combines the three octaves into k."""
    thirds = np.asarray(thirds, float)
    if thirds.shape != (3,):
        raise ValueError("an octave holds three one-third-octave bands")
    return float(np.mean(thirds))


def round_db(x: float) -> int:
    """Whole dB as reported (7.3); halves are rounded up (30.5 -> 31), which is the safe side
    for a maximum level."""
    return int(np.floor(x + 0.5))
