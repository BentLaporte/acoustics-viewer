"""Checks the parser against values read from SvanPC++ ("Total results", LZeq SR,
1/3 octave 0.8 Hz ... 20 kHz, integrated over 10 s) for samples/L1.SVL."""
from pathlib import Path

import numpy as np
import pytest

from svl.parser import read_svl, N_BANDS, ISO_SLICE, ISO_BANDS

SAMPLE = Path(__file__).parent.parent / "samples" / "L1.SVL"
pytestmark = pytest.mark.skipif(not SAMPLE.exists(), reason="sample file missing")

SVANPC_LZEQ_10S = np.array([float(x) for x in """
48.2 58.4 55.2 58.1 55.5 52.9 50.5 49.2 48.1 48.3 44.8 47.9 44.4 35.8 39.5
41.4 46.8 68.8 69.0 87.8 89.7 88.3 93.0 90.3 87.4 85.0 85.0 86.8 87.9 84.3
84.8 86.3 86.9 86.9 87.8 87.0 87.0 84.0 82.0 80.2 77.4 70.8 58.2 50.3 39.5
""".split()])


def test_header():
    f = read_svl(SAMPLE)
    assert f.name == "L1"
    assert f.duration_s == 10


def test_lzeq_matches_svanpc():
    f = read_svl(SAMPLE)
    diff = np.abs(np.round(f.leq_total(), 1) - SVANPC_LZEQ_10S)
    # both sides are rounded to 0.1 dB, so a one-digit difference is possible
    assert diff.max() <= 0.1 + 1e-6, diff.max()  # one last-digit rounding step


def test_iso_band_slice():
    assert len(ISO_BANDS) == 16 and ISO_BANDS[0] == 100 and ISO_BANDS[-1] == 3150
    assert ISO_SLICE.stop - ISO_SLICE.start == 16


def test_laeq_plausible():
    # broadband LAeq of the file (SvanPC's 10 s value in the file is 97.34 dB)
    f = read_svl(SAMPLE)
    assert abs(f.laeq_total() - 97.34) < 0.1
