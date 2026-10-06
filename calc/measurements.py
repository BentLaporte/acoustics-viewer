"""Loading and averaging of several measurement files (positions, decays)."""
from __future__ import annotations

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
class FileInfo:
    """What the report says about one measurement file."""
    name: str                          # file name only, never the folder
    measured_at: datetime | None       # date and time of the measurement (2 s resolution)
    instrument: str | None             # e.g. 'SV 977D'
    serial: int | None


def _info(path: Path, f) -> FileInfo:
    d = f.device
    return FileInfo(path.name, f.measured_at, d.label if d else None, d.serial if d else None)


def load_levels_info(paths):
    """Like load_levels, plus a FileInfo per file."""
    files = [(p, read_svl(p)) for p in as_list(paths)]
    spectra = [f.leq_total()[ISO_SLICE] for _, f in files]
    levels = spectra[0] if len(spectra) == 1 else energy_average(spectra, axis=0)
    return levels, [_info(p, f) for p, f in files]


def load_levels(paths) -> np.ndarray:
    """Energy average of the whole-file LZeq spectra of one or more files (positions),
    100 ... 3150 Hz."""
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


def load_rt(paths, kind: str):
    """Reverberation time per band (100 ... 3150 Hz): arithmetic mean over the decays.

    Returns (T, n) where n is the number of files that had a value in each band. A band
    missing in some files is averaged over the files that have it; if no file has it, T is NaN.
    """
    t, n, _ = load_rt_info(paths, kind)
    return t, n
