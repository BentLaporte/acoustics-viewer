"""Installation noise: NBN S 01-400-1:2022 clause 4.4 formulas, and LAeq / LAFmax from SVL files.

The sample file installatiegeluid_L22.SVL (SV 977D, 10 s, 14/10/2026 16:22:05) is compared with
SvanPC++ "Main results for sound", profile P1 (A, Fast), and its 1/3 Oct Leq (Total A 44.5).
Sample tests skip when the file is not present.
"""
from pathlib import Path

import numpy as np
import pytest

from calc.nbn_s01400 import reverberation_index, standardized_level
from svl.parser import Second, SvlError, SvlFile, read_svl

SAMPLES = Path(__file__).parent.parent / "samples"
L22 = SAMPLES / "installatiegeluid_L22.SVL"


# --- formulas (hand-calculated values) -------------------------------------------------------

def test_reverberation_index_is_zero_at_t0():
    assert reverberation_index(0.6, 0.5, 0.4) == pytest.approx(0.0, abs=1e-12)  # mean = 0.5 s


def test_reverberation_index():
    # 10 lg((1.0 + 0.8 + 0.6) / 1.5) = 10 lg 1.6
    assert reverberation_index(1.0, 0.8, 0.6) == pytest.approx(2.0412, abs=1e-4)


def test_standardized_level_three_positions():
    # 10 lg((10^4 + 10^4.3 + 10^4.6) / 3) = 43.6651; minus k = 10 lg 1.6 = 2.0412
    assert standardized_level([40, 43, 46], 0.0) == pytest.approx(43.6651, abs=1e-4)
    assert standardized_level([40, 43, 46], 2.0412) == pytest.approx(41.6239, abs=1e-4)


def test_standardized_level_equal_positions_and_single_position():
    assert standardized_level([35.0, 35.0, 35.0], 1.0) == pytest.approx(34.0)
    assert standardized_level(35.0, 1.0) == pytest.approx(34.0)       # one position: allowed here


def test_standardized_level_needs_a_level():
    with pytest.raises(ValueError):
        standardized_level([], 0.0)


# --- time window and LAFmax on a fabricated file ---------------------------------------------

def _second(laeq: float, lafmax: float) -> Second:
    broadband = np.zeros((3, 3))
    broadband[2, 0] = laeq                                     # LAeq of the Leq spectrum
    extra = np.zeros(12)
    extra[0:4] = [lafmax + 10, lafmax, laeq - 2, laeq]         # profile 1: peak, max, min, eq
    return Second(spectra=np.zeros((3, 45)), broadband=broadband, extra=extra)


def _file(seconds) -> SvlFile:
    return SvlFile(path=Path("x.SVL"), name="x", serial="", seconds=seconds)


def test_window_selects_seconds():
    f = _file([_second(40, 45), _second(50, 60), _second(40, 42)])
    assert f.lafmax() == 60
    assert f.lafmax(2, 3) == 42                     # only the last second
    assert f.laeq(0, 1) == pytest.approx(40)
    # energy mean of 40 and 50 dB: 10 lg((10^4 + 10^5) / 2) = 47.404
    assert f.laeq(0, 2) == pytest.approx(47.404, abs=1e-3)
    assert f.laeq_total() == pytest.approx(f.laeq(0, 3))


@pytest.mark.parametrize("start, end", [(-1, 2), (2, 2), (0, 4), (0.5, 2)])
def test_window_outside_or_not_whole_seconds_is_refused(start, end):
    f = _file([_second(40, 45)] * 3)
    with pytest.raises(ValueError):
        f.laeq(start, end)


def test_lafmax_refuses_profile_that_is_not_a_weighted():
    s = _second(40, 45)
    s.extra[3] = 60.0                               # profile 1 eq is not the LAeq (e.g. Z)
    with pytest.raises(SvlError, match="profile 1"):
        _file([s]).lafmax()


# --- sample file against SvanPC++ ------------------------------------------------------------

def shown(x: float) -> float:
    """x as SvanPC++ shows it: one decimal, halves rounded up (Python's round(60.05, 1) gives
    60.0, because 60.05 is stored as 60.04999... and ties go to the even digit)."""
    return float(np.floor(x * 10 + 0.5 + 1e-9)) / 10


@pytest.mark.skipif(not L22.exists(), reason="sample file not present")
def test_sample_matches_svanpc_main_results():
    f = read_svl(L22)
    assert f.duration_s == 10
    assert shown(f.laeq()) == 44.5               # Total A, and LEPd / Lden of P1
    assert shown(f.lafmax()) == 46.1             # P1 (A, Fast) Lmax
    profile1 = np.array([s.profiles[0] for s in f.seconds])
    assert shown(profile1[:, 2].min()) == 43.1  # P1 Lmin
    assert shown(profile1[:, 0].max()) == 60.1  # P1 Lpeak
