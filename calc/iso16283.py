"""Field quantities from ISO 16283-1 (airborne) and -2 (impact)."""
from __future__ import annotations

import numpy as np

T0 = 0.5     # reference reverberation time, s


def dnt(l_source, l_receiving, t_receiving):
    """Standardized level difference DnT = (L1 - L2) + 10 lg(T/T0), per band."""
    return (np.asarray(l_source, float) - np.asarray(l_receiving, float)
            + 10 * np.log10(np.asarray(t_receiving, float) / T0))


def lnt(l_receiving, t_receiving):
    """Standardized impact sound pressure level L'nT = Li - 10 lg(T/T0), per band."""
    return (np.asarray(l_receiving, float)
            - 10 * np.log10(np.asarray(t_receiving, float) / T0))
