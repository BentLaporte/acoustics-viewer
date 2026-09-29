"""Impact sound insulation from three measurement files (no GUI dependencies)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .iso16283 import lnt
from .iso717 import BANDS, Rating, impact_adaptation_term, rate_impact
from .levels import LIMIT, background_correction
from .measurements import as_list, load_levels, load_rt


@dataclass
class ImpactResult:
    bands: np.ndarray        # 100 ... 3150 Hz
    li_raw: np.ndarray       # tapping machine level in the receiving room, as measured
    lb: np.ndarray           # background level in the receiving room
    li: np.ndarray           # level after background correction
    status: np.ndarray       # ok / corrected / limit per band
    t: np.ndarray            # reverberation time of the receiving room (NaN if missing)
    t_kind: str              # 'edt' | 't20' | 't30'
    lnt: np.ndarray          # standardized impact sound pressure level L'nT
    names: dict              # role -> list of file names (one per position / decay)
    t_counts: np.ndarray | None = None   # decays that contributed to T, per band
    rating: Rating | None = None   # ISO 717-2 rating of L'nT (None if a band is missing)
    ci: int | None = None          # adaptation term C_I (100 - 2500 Hz)

    @property
    def n_limit(self) -> int:
        return int(np.sum(self.status == LIMIT))


def compute_impact(tapping, background, rt, rt_kind: str = "t30") -> ImpactResult:
    """Read the files and compute Li, background correction, L'nT, L'nT,w and C_I.

    Every argument is one path or a list of paths (tapping machine positions are
    energy-averaged, reverberation time decays are averaged arithmetically per band).
    """
    li_raw = load_levels(tapping)
    lb = load_levels(background)
    t, t_counts = load_rt(rt, rt_kind)

    li, status = background_correction(li_raw, lb)
    lnt_values = lnt(li, t)
    rating = ci = None
    if np.all(np.isfinite(lnt_values)):
        rating = rate_impact(lnt_values)
        ci = impact_adaptation_term(lnt_values, rating.value)
    return ImpactResult(
        bands=BANDS.copy(), li_raw=li_raw, lb=lb, li=li, status=status, t=t,
        t_kind=rt_kind.lower(), lnt=lnt_values,
        names={k: [p.name for p in as_list(v)] for k, v in
               (("tapping", tapping), ("background", background), ("rt", rt))},
        t_counts=t_counts, rating=rating, ci=ci)
