"""Level arithmetic shared by the ISO 16283 calculations."""
from __future__ import annotations

import numpy as np

# status per band after background correction
OK, CORRECTED, LIMIT = "ok", "corrected", "limit"


def round_tenth(levels):
    """Reduce levels to one decimal place, halves up, as ISO 717-1 4.4 footnote 1, ISO 717-2
    4.3.1 footnote 1 and ISO 16283-1/-2 9.2 prescribe: 'multiply by 10, add 0,5, take the
    integer part and divide by 10' (XX,X5 -> XX,X + 0,1). Not numpy's round, which rounds
    halves to the even digit.

    The 1e-9 makes up for binary floating point: 44.35 is stored as 44.34999..., and without
    it would become 44.3. The levels have 0.01 dB resolution, so the tolerance never changes
    a real value."""
    levels = np.asarray(levels, float)
    return np.floor(levels * 10 + 0.5 + 1e-9) / 10


def energy_average(levels, axis=0):
    """Energy average of levels in dB (e.g. several microphone positions)."""
    levels = np.asarray(levels, float)
    return 10 * np.log10(np.mean(10 ** (levels / 10), axis=axis))


def background_correction(l_sb, l_b):
    """Background noise correction per band (ISO 16283-1, 'signal + background' L_sb).

    L_sb and L_b are first reduced to one decimal place (9.2, see round_tenth), then
    delta = L_sb - L_b
      delta >= 10 dB      : no correction
      6 dB < delta < 10   : L = 10 lg(10^(L_sb/10) - 10^(L_b/10))
      delta <= 6 dB       : L = L_sb - 1.3 dB, and the band is only a limit value

    Returns (corrected levels, status array of OK / CORRECTED / LIMIT).
    """
    l_sb = round_tenth(l_sb)
    l_b = round_tenth(l_b)
    # both are multiples of 0.1, so the difference is too; rounding it again removes the
    # floating-point noise of the subtraction (54.3 - 48.3 = 5.999999...) before comparing
    delta = np.round(l_sb - l_b, 6)
    out = l_sb.copy()
    status = np.full(l_sb.shape, OK, dtype=object)

    mid = (delta > 6) & (delta < 10)
    out[mid] = 10 * np.log10(10 ** (l_sb[mid] / 10) - 10 ** (l_b[mid] / 10))
    status[mid] = CORRECTED

    low = delta <= 6
    out[low] = l_sb[low] - 1.3
    status[low] = LIMIT
    return out, status
