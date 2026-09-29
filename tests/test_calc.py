"""Arithmetic checks for calc/. Expected values are derived by hand from the
procedure in the standards, NOT taken from the standards' worked examples
(those were not available). The reference tables were checked against the
standard by the project owner."""
import numpy as np
import pytest

from calc.iso16283 import dnt, lnt
from calc.iso717 import (REF_AIRBORNE, REF_IMPACT, SPECTRUM_1_PINK, adaptation_term,
                         airborne_summary, rate_airborne, rate_impact)
from calc.levels import CORRECTED, LIMIT, OK, background_correction, energy_average


def test_energy_average():
    assert energy_average([60, 60]) == pytest.approx(60)
    assert energy_average([60, 70]) == pytest.approx(10 * np.log10((1e6 + 1e7) / 2))


def test_background_three_regions():
    l_sb = np.array([70.0, 65.0, 62.0])
    l_b = np.array([50.0, 58.0, 60.0])          # deltas 20, 7, 2
    out, st = background_correction(l_sb, l_b)
    assert list(st) == [OK, CORRECTED, LIMIT]
    assert out[0] == 70.0
    assert out[1] == pytest.approx(10 * np.log10(10 ** 6.5 - 10 ** 5.8))
    assert out[2] == pytest.approx(62.0 - 1.3)


def test_background_boundaries():
    out, st = background_correction(np.array([60.0, 66.0, 70.0, 70.1]), np.full(4, 60.0))
    assert st[0] == LIMIT and st[1] == CORRECTED and st[2] == CORRECTED and st[3] == OK


def test_dnt_and_lnt_reference_time():
    assert dnt(80, 50, 0.5) == pytest.approx(30)                 # T = T0 -> no term
    assert dnt(80, 50, 1.0) == pytest.approx(30 + 10 * np.log10(2))
    assert lnt(60, 0.5) == pytest.approx(60)
    assert lnt(60, 1.0) == pytest.approx(60 - 10 * np.log10(2))


def test_airborne_curve_itself_rates_54():
    r = rate_airborne(REF_AIRBORNE)
    # the reference curve fits perfectly at shift 0; shifting up by 2 gives
    # 16 * 2 = 32.0 dB of deviations, still allowed -> largest allowed shift is 2
    assert r.shift == 2 and r.value == 54 and r.unfavourable_sum == pytest.approx(32.0)


def test_airborne_flat_excess():
    # values = curve + 10: shift s > 10 gives 16 * (s - 10) <= 32 -> s = 12
    r = rate_airborne(REF_AIRBORNE + 10)
    assert r.shift == 12 and r.value == 64


def test_airborne_limit_is_inclusive_and_strict_above():
    v = REF_AIRBORNE.astype(float)
    v[0] -= 31.0                                # one band 31 dB below: sum 31 at shift 0
    r = rate_airborne(v)
    assert r.unfavourable_sum <= 32.0
    # one step further up must break the limit
    dev_next = np.clip((REF_AIRBORNE + r.shift + 1) - np.round(v, 1), 0, None).sum()
    assert dev_next > 32.0


def test_impact_curve_itself():
    r = rate_impact(REF_IMPACT)
    # smallest position with sum above <= 32: curve moved down by 2 (16 * 2 = 32)
    assert r.shift == -2 and r.value == 58


def test_impact_flat_offset():
    # values = curve - 10: shift s < -10 gives 16 * (-10 - s)... i.e. s = -12 allowed
    r = rate_impact(REF_IMPACT - 10)
    assert r.shift == -12 and r.value == 48


def test_adaptation_flat_spectrum_identity():
    # flat values c: X_A = c - 10 lg sum 10^(L_i/10), computed independently here
    c = 60.0
    x_a = c - 10 * np.log10(np.sum(10 ** (SPECTRUM_1_PINK / 10)))
    assert adaptation_term(np.full(16, c), SPECTRUM_1_PINK, 50) == int(np.round(x_a - 50))


def test_rating_needs_all_bands():
    with pytest.raises(ValueError):
        rate_airborne(np.append(REF_AIRBORNE[:-1], np.nan))
    with pytest.raises(ValueError):
        rate_airborne(REF_AIRBORNE[:-1])


def test_summary_keys():
    s = airborne_summary(REF_AIRBORNE + 5.0)
    assert set(s) == {"rating", "w", "C", "Ctr"}
