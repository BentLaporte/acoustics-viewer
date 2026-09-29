"""Level arithmetic shared by the ISO 16283 calculations."""
from __future__ import annotations

import numpy as np

# status per band after background correction
OK, CORRECTED, LIMIT = "ok", "corrected", "limit"


def energy_average(levels, axis=0):
    """Energy average of levels in dB (e.g. several microphone positions)."""
    levels = np.asarray(levels, float)
    return 10 * np.log10(np.mean(10 ** (levels / 10), axis=axis))


def background_correction(l_sb, l_b):
    """Background noise correction per band (ISO 16283-1, 'signal + background' L_sb).

    delta = L_sb - L_b
      delta > 10 dB        : no correction
      6 dB <= delta <= 10  : L = 10 lg(10^(L_sb/10) - 10^(L_b/10))
      delta < 6 dB         : L = L_sb - 1.3 dB, and the band is only an upper limit

    Returns (corrected levels, status array of OK / CORRECTED / LIMIT).
    """
    l_sb = np.asarray(l_sb, float)
    l_b = np.asarray(l_b, float)
    delta = l_sb - l_b
    out = l_sb.copy()
    status = np.full(l_sb.shape, OK, dtype=object)

    mid = (delta >= 6) & (delta <= 10)
    out[mid] = 10 * np.log10(10 ** (l_sb[mid] / 10) - 10 ** (l_b[mid] / 10))
    status[mid] = CORRECTED

    low = delta < 6
    out[low] = l_sb[low] - 1.3
    status[low] = LIMIT
    return out, status
