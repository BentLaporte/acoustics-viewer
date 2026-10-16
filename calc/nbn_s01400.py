"""Installation noise quantities of NBN S 01-400-1:2022, clause 4.4 (pure functions).

  k          = 10 lg((T500 + T1000 + T2000) / (3 T0))           reverberation index
  L_Aeq,nT   = 10 lg((10^(L_Aeq,1/10) + 10^(L_Aeq,2/10) + 10^(L_Aeq,3/10)) / 3) - k
  L_AFmax,nT = the same formula with the L_AFmax values

L_1 is measured in the corner of the room with the acoustically hardest walls, 50 cm from those
walls; L_2 and L_3 in the reverberant field, at least 1.5 m from the sources. T500, T1000 and T2000
are octave-band reverberation times (NBN EN ISO 10052). L_Aeq,nT is used for stationary
installations, L_AFmax,nT for transient ones.
"""
from __future__ import annotations

import numpy as np

from .iso16283 import T0
from .levels import energy_average

N_POSITIONS = 3      # the standard: one corner position and two in the reverberant field


def reverberation_index(t500: float, t1000: float, t2000: float) -> float:
    """k = 10 lg((T500 + T1000 + T2000) / (3 T0)), octave-band reverberation times in s."""
    return float(10 * np.log10((t500 + t1000 + t2000) / (3 * T0)))


def standardized_level(levels, k: float) -> float:
    """L_nT = energy average of the position levels - k (for L_Aeq,nT and for L_AFmax,nT).

    The standard prescribes exactly three positions (N_POSITIONS); this function takes any
    number so that a measurement with fewer can still be shown. Flagging that deviation is up
    to the caller."""
    levels = np.atleast_1d(np.asarray(levels, float))
    if levels.size == 0:
        raise ValueError("no level given")
    return float(energy_average(levels)) - k
