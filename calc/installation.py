"""Installation noise (service equipment sound) from measurement files (no GUI dependencies).

ISO 10052:2021 as used by NBN S 01-400-1:2022: L_Aeq,nT (stationary installations) or
L_AFmax,nT (transient ones) from A-weighted levels, standardized with one reverberation index k
from the octave bands 500, 1000 and 2000 Hz. See calc/iso10052.py for the formulas.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from svl.parser import read_svl
from svl.rt import read_rt

from .iso10052 import (BACKGROUND_MARGIN_DB, K_OCTAVES, N_MEASUREMENTS, octave_rt,
                       reverberation_index, round_db, standardized_level)
from .levels import energy_average
from .measurements import FileInfo, Recording, _info, as_list, as_recordings  # noqa: F401

QUANTITIES = {"laeq": "LAeq,nT", "lafmax": "LAFmax,nT"}
METHODS = {
    "positions": "one measurement close to the corner and two in the reverberant field "
                 "(ISO 10052 6.3.4)",
    "integrated": "integrated method: moving microphone through the room",
}
# the three one-third-octave bands inside each octave of k
OCTAVE_THIRDS = {500: (400, 500, 630), 1000: (800, 1000, 1250), 2000: (1600, 2000, 2500)}


@dataclass
class InstallationResult:
    quantity: str                 # 'laeq' | 'lafmax'
    method: str                   # 'positions' | 'integrated'
    recordings: list[Recording]
    levels: np.ndarray            # LAeq or LAFmax of every recording, dB
    durations: list[int]          # seconds used of every recording
    level: float                  # L_XY: energy average of the recordings
    background: float | None      # LAeq of the background (energy average of the files)
    margins: np.ndarray | None    # level - background LAeq, per recording (for LAFmax too: our
                                  # choice, the standard does not say which background level)
    t_thirds: dict                # one-third-octave band (Hz) -> T in s (mean over the files)
    t20_used: dict                # one-third-octave band (Hz) -> files where T20 replaced T30
    t_octaves: dict               # 500 / 1000 / 2000 -> octave T in s
    k: float                      # reverberation index, dB
    lnt: float                    # L_XY,nT unrounded
    info: dict = field(default_factory=dict)   # role -> list of FileInfo
    notes: list[str] = field(default_factory=list)

    @property
    def value(self) -> int:
        """L_XY,nT as reported: whole dB."""
        return round_db(self.lnt)

    @property
    def symbol(self) -> str:
        return QUANTITIES[self.quantity]

    @property
    def background_affected(self) -> bool:
        """A recording less than 6 dB above the background: the value is overestimated."""
        return self.margins is not None and bool(np.any(self.margins < BACKGROUND_MARGIN_DB))

    @property
    def lnt_without_background(self) -> float | None:
        """L_Aeq,nT with the background energy subtracted from every recording: the lowest the
        installation noise can be, assuming the background during the measurement was the
        background that was measured. Only used to decide a failure (fails_anyway); the
        reported value stays uncorrected (ISO 10052 6.2.1).

        None without a background, for LAFmax (the maximum of the background is not known)
        and when no recording is above the background (then nothing is left to judge)."""
        if self.background is None or self.quantity != "laeq":
            return None
        energy = 10 ** (self.levels / 10) - 10 ** (self.background / 10)
        energy = np.clip(energy, 0, None)              # at or below the background: 0
        if not np.any(energy > 0):
            return None
        return float(10 * np.log10(np.mean(energy))) - self.k

    def fails_anyway(self, requirement: int, tolerance: int = 0) -> bool:
        """Does the installation exceed the requirement (+ tolerance) even with the background
        subtracted? Then a failure is sure although the level was close to the background."""
        lo = self.lnt_without_background
        return lo is not None and round_db(lo) > requirement + tolerance


def _rt_thirds(paths) -> tuple[dict, dict, list[FileInfo]]:
    """T per one-third-octave band of k: T30, and T20 where a file has no T30 for a band.
    Several files (decays) are averaged arithmetically per band."""
    thirds = [f for octave in K_OCTAVES for f in OCTAVE_THIRDS[octave]]
    files = [(p, read_rt(p)) for p in as_list(paths)]
    values, t20_used = [], {}
    for p, f in files:
        t30, t20 = f.at(thirds, "t30"), f.at(thirds, "t20")
        for hz, a, b in zip(thirds, t30, t20):
            if not np.isfinite(a) and np.isfinite(b):
                t20_used.setdefault(hz, []).append(p.name)
        values.append(np.where(np.isfinite(t30), t30, t20))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)          # all-NaN band -> NaN
        mean = np.nanmean(np.array(values), axis=0)
    return dict(zip(thirds, mean.tolist())), t20_used, [_info(p, f) for p, f in files]


def compute_installation(recordings, rt, background=None, quantity: str = "laeq",
                         method: str = "integrated") -> InstallationResult:
    """Read the files and compute L_Aeq,nT or L_AFmax,nT.

    recordings: Recording objects, paths or 'file@start-end' strings. method 'positions' needs
    exactly three (the corner position first), 'integrated' takes one or more (energy average).
    rt: reverberation time file(s) of the room. background: optional level file(s); the level is
    checked against it, never corrected (ISO 10052 6.2.1).
    """
    if quantity not in QUANTITIES:
        raise ValueError(f"quantity must be one of {', '.join(QUANTITIES)}")
    if method not in METHODS:
        raise ValueError(f"method must be one of {', '.join(METHODS)}")
    recs = [r if isinstance(r, Recording) else Recording.parse(r)
            for r in ([recordings] if isinstance(recordings, (str, Path, Recording)) else recordings)]
    if not recs:
        raise ValueError("no level file given")
    if method == "positions" and len(recs) != N_MEASUREMENTS:
        raise ValueError(f"the position method needs {N_MEASUREMENTS} measurements (corner "
                         f"first, then two in the reverberant field), got {len(recs)}")

    files = [read_svl(r.path) for r in recs]
    measure = (lambda f, r: f.laeq(r.start, r.end)) if quantity == "laeq" else \
              (lambda f, r: f.lafmax(r.start, r.end))
    levels = np.array([measure(f, r) for f, r in zip(files, recs)])
    durations = [len(f.usable(r.start, r.end)) for f, r in zip(files, recs)]   # used seconds
    info = {"level": [_info(r.path, f) for r, f in zip(recs, files)]}

    t_thirds, t20_used, info["rt"] = _rt_thirds(rt)
    t_octaves = {o: octave_rt([t_thirds[hz] for hz in OCTAVE_THIRDS[o]]) for o in K_OCTAVES}
    missing = [o for o, t in t_octaves.items() if not np.isfinite(t)]
    if missing:
        raise ValueError("no reverberation time (T30 or T20) in the octave band(s) "
                         + ", ".join(f"{o} Hz" for o in missing))
    k = reverberation_index(*(t_octaves[o] for o in K_OCTAVES))

    bg = margins = None
    if background is not None:
        bg_files = [(r, read_svl(r.path)) for r in as_recordings(background)]
        bg = float(energy_average([f.laeq(r.start, r.end) for r, f in bg_files]))
        margins = levels - bg
        info["background"] = [_info(r.path, f, r.window_text) for r, f in bg_files]

    res = InstallationResult(
        quantity=quantity, method=method, recordings=recs, levels=levels, durations=durations,
        level=float(energy_average(levels)), background=bg, margins=margins, t_thirds=t_thirds,
        t20_used=t20_used, t_octaves=t_octaves, k=k, lnt=standardized_level(levels, k), info=info)
    res.notes = _notes(res)
    return res


def _notes(r: InstallationResult) -> list[str]:
    notes = []
    if r.method == "integrated":
        notes.append("Measured with the integrated method (moving microphone) instead of one "
                     "measurement close to the corner and two in the reverberant field "
                     "(ISO 10052 6.3.4).")
    if r.t20_used:
        bands = ", ".join(f"{int(hz)} Hz" for hz in sorted(r.t20_used))
        notes.append(f"T20 used where T30 is not available: {bands}.")
    if r.background is None:
        notes.append("Background noise not checked (no background file).")
    elif r.background_affected:
        notes.append(f"Level less than {BACKGROUND_MARGIN_DB:.0f} dB above the background "
                     "noise: reported as measured, without correction; the value is "
                     "overestimated by an unknown amount (ISO 10052 6.2.1).")
    return notes


def check_requirement(r: InstallationResult, requirement: int | None) -> str:
    """'none' | 'complies' | 'fails' | 'inconclusive'. The requirement is a maximum. A pass is
    always reliable (background noise can only raise the level); a failure is inconclusive when
    the level was within 6 dB of the background, unless it fails even with the background
    subtracted (InstallationResult.fails_anyway)."""
    if requirement is None:
        return "none"
    if r.value <= requirement:
        return "complies"
    if r.background_affected and not r.fails_anyway(requirement):
        return "inconclusive"
    return "fails"
