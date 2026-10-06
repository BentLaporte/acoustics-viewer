"""A fabricated airborne measurement for the documentation and the tests of the JSON output.

NOT real data: the levels are made up (the shape of a plausible wall), so the example files in
docs/ can be regenerated and checked without publishing any client measurement.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np

from .airborne import AirborneResult
from .building import Evaluated
from .iso16283 import dnt
from .iso717 import BANDS, airborne_summary
from .levels import background_correction
from .measurements import FileInfo


def example_airborne() -> Evaluated:
    """'Wall between room A and room B' with a requirement of 54 dB."""
    l1 = np.array([88, 89, 88, 86, 85, 85, 86, 86, 85, 84, 85, 85, 86, 86, 86, 86], float)
    l2_raw = np.array([52, 53, 52, 47, 44, 44, 43, 41, 34, 31, 31, 29, 26, 26, 24, 21], float)
    lb = np.array([26, 17, 18, 22, 21, 11, 9, 3, 3, 2, 5, 8, 4, 4, 5, 6], float)
    t = np.array([2.5, 2.0, 2.5, 3.1, 1.7, 1.4, 1.1, 1.3, 1.1, 1.0, 1.0, 0.95, 0.8, 0.78, 0.72,
                  0.74])
    l2, status = background_correction(l2_raw, lb)
    dnt_values = dnt(l1, l2, t)
    summary = airborne_summary(dnt_values)
    info = {
        "source": [FileInfo("A.L1.SVL", datetime(2026, 1, 15, 10, 2, 4), "SV 977D", 100001)],
        "receiver": [FileInfo("B.L1.SVL", datetime(2026, 1, 15, 10, 2, 6), "SV 977D", 100002)],
        "background": [FileInfo("B.L9.SVL", datetime(2026, 1, 15, 10, 40, 0), "SV 977D", 100002)],
        "rt": [FileInfo("B.L8.SVL", datetime(2026, 1, 15, 10, 30, 12), "SV 977D", 100002)]}
    result = AirborneResult(
        bands=BANDS.copy(), l1=l1, l2_raw=l2_raw, lb=lb, l2=l2, status=status, t=t, t_kind="t30",
        d=l1 - l2, dnt=dnt_values, names={k: [i.name for i in v] for k, v in info.items()},
        t_counts=np.ones(16, int), info=info, rating=summary["rating"], c=summary["C"],
        ctr=summary["Ctr"])
    return Evaluated("airborne", "airborne room A to room B", "room A", "room B", result,
                     requirement=54)
