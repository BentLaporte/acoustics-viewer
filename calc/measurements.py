"""Loading and averaging of several measurement files (positions, decays)."""
from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from svl.parser import ISO_SLICE, read_svl
from svl.rt import read_rt

from .iso717 import BANDS
from .levels import energy_average


def as_list(paths) -> list[Path]:
    """One path or a list of paths -> non-empty list of Paths."""
    if isinstance(paths, (str, Path)):
        paths = [paths]
    out = [Path(p) for p in paths]
    if not out:
        raise ValueError("no file given")
    return out


@dataclass(frozen=True)
class Recording:
    """One level file, optionally only a part of it: seconds start ... end (end exclusive)."""
    path: Path
    start: int = 0
    end: int | None = None

    @classmethod
    def parse(cls, spec) -> "Recording":
        """'file.SVL' or 'file.SVL@start-end' (whole seconds, end may be left out: '@5-')."""
        spec = str(spec)
        m = re.fullmatch(r"(.+)@(\d+)-(\d*)", spec)
        if not m:
            return cls(Path(spec))
        return cls(Path(m[1]), int(m[2]), int(m[3]) if m[3] else None)

    @property
    def windowed(self) -> bool:
        return not (self.start == 0 and self.end is None)

    @property
    def spec(self) -> str:
        """The text form parse() reads back: 'file.SVL' or 'file.SVL@start-end'."""
        if not self.windowed:
            return str(self.path)
        return f"{self.path}@{self.start}-{'' if self.end is None else self.end}"

    @property
    def window_text(self) -> str:
        return "" if self.start == 0 and self.end is None else \
            f"{self.start}-{'' if self.end is None else self.end} s"


def as_recordings(paths) -> list[Recording]:
    """One or more level files -> Recordings. A file may carry a time window as
    'file.SVL@start-end' (whole seconds; how the project file stores a window on a background
    file, and what the command line accepts)."""
    if isinstance(paths, (str, Path, Recording)):
        paths = [paths]
    out = [p if isinstance(p, Recording) else Recording.parse(p) for p in paths]
    if not out:
        raise ValueError("no file given")
    return out


@dataclass(frozen=True)
class FileInfo:
    """What the report says about one measurement file."""
    name: str                          # file name only, never the folder
    measured_at: datetime | None       # date and time of the measurement (2 s resolution)
    instrument: str | None             # e.g. 'SV 977D'
    serial: int | None
    flagged: tuple[int, ...] = ()      # seconds (0-based) marked by the instrument, left out
    window: str = ""                   # part of the file used, e.g. '0-4 s' ('' = whole file)


def _info(path: Path, f, window: str = "") -> FileInfo:
    d = f.device
    return FileInfo(path.name, f.measured_at, d.label if d else None, d.serial if d else None,
                    tuple(getattr(f, "flagged_seconds", ())),     # RT files have no flags
                    window)


def load_levels_info(paths):
    """Like load_levels, plus a FileInfo per file. A file may be 'file.SVL@start-end'."""
    files = [(r, read_svl(r.path)) for r in as_recordings(paths)]
    spectra = [f.leq_total(r.start, r.end)[ISO_SLICE] for r, f in files]
    levels = spectra[0] if len(spectra) == 1 else energy_average(spectra, axis=0)
    return levels, [_info(r.path, f, r.window_text) for r, f in files]


def load_levels(paths) -> np.ndarray:
    """Energy average of the LZeq spectra of one or more files (positions), 100 ... 3150 Hz;
    whole files, or the window of a 'file.SVL@start-end'."""
    return load_levels_info(paths)[0]


def load_rt_info(paths, kind: str):
    """Like load_rt, plus a FileInfo per file: returns (T, n, infos)."""
    files = [(p, read_rt(p)) for p in as_list(paths)]
    values = np.array([f.at(BANDS, kind) for _, f in files])
    n = np.sum(np.isfinite(values), axis=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)      # all-NaN bands -> NaN
        t = np.nanmean(values, axis=0)
    return t, n, [_info(p, f) for p, f in files]


def load_rt_fallback(paths, kind: str):
    """Like load_rt_info, but with kind 't30' a file without T30 in a band gives its T20 there
    (the decay range was too short for 30 dB; T20 is a valid evaluation range of ISO 3382-2,
    to which ISO 16283 refers). Bent's rule, as for installation noise.

    Returns (T, n, infos, t20_used) with t20_used: band (Hz) -> names of the files concerned."""
    files = [(p, read_rt(p)) for p in as_list(paths)]
    values, t20_used = [], {}
    for p, f in files:
        v = f.at(BANDS, kind)
        if kind.lower() == "t30":
            t20 = f.at(BANDS, "t20")
            fill = ~np.isfinite(v) & np.isfinite(t20)
            for hz in BANDS[fill]:
                t20_used.setdefault(float(hz), []).append(p.name)
            v = np.where(fill, t20, v)
        values.append(v)
    values = np.array(values)
    n = np.sum(np.isfinite(values), axis=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)      # all-NaN bands -> NaN
        t = np.nanmean(values, axis=0)
    return t, n, [_info(p, f) for p, f in files], t20_used


def load_rt(paths, kind: str):
    """Reverberation time per band (100 ... 3150 Hz): arithmetic mean over the decays.

    Returns (T, n) where n is the number of files that had a value in each band. A band
    missing in some files is averaged over the files that have it; if no file has it, T is NaN.
    """
    t, n, _ = load_rt_info(paths, kind)
    return t, n
