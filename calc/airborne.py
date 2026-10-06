"""Airborne sound insulation from four measurement files (no GUI dependencies)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .iso16283 import dnt
from .iso717 import BANDS, Rating, airborne_summary
from .levels import LIMIT, background_correction
from .measurements import load_levels_info, load_rt_info


@dataclass
class AirborneResult:
    bands: np.ndarray        # 100 ... 3150 Hz
    l1: np.ndarray           # source room level (LZeq)
    l2_raw: np.ndarray       # receiving room level as measured
    lb: np.ndarray           # receiving room background level
    l2: np.ndarray           # receiving room level after background correction
    status: np.ndarray       # ok / corrected / limit per band
    t: np.ndarray            # reverberation time of the receiving room (NaN if missing)
    t_kind: str              # 'edt' | 't20' | 't30'
    d: np.ndarray            # level difference L1 - L2
    dnt: np.ndarray          # standardized level difference (NaN where T missing)
    names: dict              # role -> list of file names (one per position / decay)
    t_counts: np.ndarray | None = None   # decays that contributed to T, per band
    info: dict | None = None             # role -> list of FileInfo (name, date and time, instrument)
    rating: Rating | None = None   # ISO 717-1 rating of DnT (None if a band is missing)
    c: int | None = None           # adaptation term C
    ctr: int | None = None         # adaptation term Ctr

    @property
    def n_limit(self) -> int:
        return int(np.sum(self.status == LIMIT))


def compute_airborne(source, receiver, background, rt, rt_kind: str = "t30") -> AirborneResult:
    """Read the files and compute levels, correction, D and DnT per band.

    Every argument is one path or a list of paths. Several level files of one room are
    energy-averaged (positions); several reverberation time files are averaged
    arithmetically per band (decays).
    """
    l1, i_source = load_levels_info(source)
    l2_raw, i_receiver = load_levels_info(receiver)
    lb, i_background = load_levels_info(background)
    t, t_counts, i_rt = load_rt_info(rt, rt_kind)
    info = {"source": i_source, "receiver": i_receiver, "background": i_background, "rt": i_rt}

    l2, status = background_correction(l2_raw, lb)
    d = l1 - l2
    dnt_values = dnt(l1, l2, t)
    rating = c = ctr = None
    if np.all(np.isfinite(dnt_values)):
        summary = airborne_summary(dnt_values)
        rating, c, ctr = summary["rating"], summary["C"], summary["Ctr"]
    return AirborneResult(
        bands=BANDS.copy(), l1=l1, l2_raw=l2_raw, lb=lb, l2=l2, status=status,
        t=t, t_kind=rt_kind.lower(), d=d, dnt=dnt_values,
        names={k: [x.name for x in v] for k, v in info.items()},
        t_counts=t_counts, info=info, rating=rating, c=c, ctr=ctr)
