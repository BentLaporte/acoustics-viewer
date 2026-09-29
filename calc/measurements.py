"""Loading and averaging of several measurement files (positions, decays)."""
from __future__ import annotations

import warnings
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


def load_levels(paths) -> np.ndarray:
    """Energy average of the whole-file LZeq spectra of one or more files (positions),
    100 ... 3150 Hz."""
    spectra = [read_svl(p).leq_total()[ISO_SLICE] for p in as_list(paths)]
    return spectra[0] if len(spectra) == 1 else energy_average(spectra, axis=0)


def load_rt(paths, kind: str):
    """Reverberation time per band (100 ... 3150 Hz): arithmetic mean over the decays.

    Returns (T, n) where n is the number of files that had a value in each band. A band
    missing in some files is averaged over the files that have it; if no file has it, T is NaN.
    """
    values = np.array([read_rt(p).at(BANDS, kind) for p in as_list(paths)])
    n = np.sum(np.isfinite(values), axis=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)      # all-NaN bands -> NaN
        t = np.nanmean(values, axis=0)
    return t, n
