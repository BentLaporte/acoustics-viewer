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


# --- calc.airborne (uses the sample files, skipped if they are not present) -------
from pathlib import Path as _P

from calc.airborne import compute_airborne

_S = _P(__file__).parent.parent / "samples"
_need = [_S / n for n in ("A_L2.SVL", "B_L2.SVL", "C_L20.SVL", "B_L11.SVL")]


@pytest.mark.skipif(not all(p.exists() for p in _need), reason="sample files missing")
def test_compute_airborne_samples():
    res = compute_airborne(*_need)
    assert len(res.bands) == 16 and res.n_limit == 0
    assert np.allclose(res.d + 10 * np.log10(res.t / 0.5), res.dnt)
    s = airborne_summary(res.dnt)
    assert (s["w"], s["C"], s["Ctr"]) == (54, -1, -4)


@pytest.mark.skipif(not all(p.exists() for p in _need), reason="sample files missing")
def test_rating_none_when_rt_band_missing():
    res = compute_airborne(*_need, rt_kind="edt")     # EDT is *** at 100 Hz in the sample
    assert res.rating is None and res.c is None
    ok = compute_airborne(*_need, rt_kind="t30")
    assert ok.rating.value == 54 and ok.rating.shift == 2
    assert ok.rating.unfavourable_sum == pytest.approx(25.8)


# --- calc.impact ----------------------------------------------------------------------
from calc.impact import compute_impact

_imp = [_S / n for n in ("B_L4.SVL", "C_L20.SVL", "B_L11.SVL")]


@pytest.mark.skipif(not all(p.exists() for p in _imp), reason="sample files missing")
def test_compute_impact_samples():
    res = compute_impact(*_imp)
    assert len(res.bands) == 16 and res.n_limit == 0
    assert np.allclose(res.li - 10 * np.log10(res.t / 0.5), res.lnt)
    r = res.rating
    assert (r.value, r.shift) == (44, -16) and r.unfavourable_sum == pytest.approx(21.7)
    # the chosen position is the lowest allowed one: one step further down breaks the limit
    below = np.clip(np.round(res.lnt, 1) - (REF_IMPACT + r.shift - 1), 0, None).sum()
    assert below > 32.0


@pytest.mark.skipif(not all(p.exists() for p in _imp), reason="sample files missing")
def test_impact_rating_none_when_rt_band_missing():
    assert compute_impact(*_imp, rt_kind="edt").rating is None


# --- C_I and averaging ----------------------------------------------------------------
from calc.iso717 import impact_adaptation_term, round_half_up
from calc.measurements import load_levels, load_rt


def test_round_half_up():
    assert [round_half_up(x) for x in (-1.5, -0.5, 0.5, 1.5, 2.4, -2.6)] == [-1, 0, 1, 2, 2, -3]


def test_ci_flat_spectrum_by_hand():
    # 50 dB in all bands: L_sum = 50 + 10 lg 15 = 61.76 dB (15 bands, 100-2500 Hz)
    assert impact_adaptation_term(np.full(16, 50.0), 45) == 2       # 61.76 - 15 - 45 = 1.76
    assert impact_adaptation_term(np.full(16, 50.0), 47) == 0       # -0.24


def test_ci_ignores_3150_hz_and_uses_energy_sum():
    v = np.full(16, 40.0)
    base = impact_adaptation_term(v, 40)
    v2 = v.copy(); v2[15] = 90.0                                    # 3150 Hz: outside 100-2500
    assert impact_adaptation_term(v2, 40) == base
    v3 = np.full(16, 0.0); v3[4] = 60.0                             # one dominant band
    assert impact_adaptation_term(v3, 45) == 0                      # 60 - 15 - 45 = 0 (others ~ 0 dB add 0.0..)


def test_ci_rounds_values_like_the_rating():
    v = np.full(16, 50.04)                                          # rated as 50.0
    assert impact_adaptation_term(v, 45) == impact_adaptation_term(np.full(16, 50.0), 45)


@pytest.mark.skipif(not all(p.exists() for p in _imp), reason="sample files missing")
def test_impact_ci_on_samples():
    res = compute_impact(*_imp)
    v = np.round(res.lnt, 1)[:15]
    l_sum = 10 * np.log10(np.sum(10 ** (v / 10)))
    assert l_sum == pytest.approx(58.07, abs=0.01)
    assert res.ci == -1 and res.rating.value + res.ci == 43


@pytest.mark.skipif(not all(p.exists() for p in _need), reason="sample files missing")
def test_averaging_levels_and_rt():
    a, b = _S / "A_L2.SVL", _S / "B_L2.SVL"
    la, lb_ = load_levels(a), load_levels(b)
    avg = load_levels([a, b])
    assert np.allclose(avg, 10 * np.log10((10 ** (la / 10) + 10 ** (lb_ / 10)) / 2))
    assert np.allclose(load_levels([a, a, a]), la)                 # identical files change nothing
    rt = _S / "B_L11.SVL"
    t1, n1 = load_rt(rt, "t30")
    t2, n2 = load_rt([rt, rt], "t30")
    assert np.allclose(t1, t2) and (n1 == 1).all() and (n2 == 2).all()
    # EDT is missing at 100 Hz in the sample: still NaN, with zero contributing decays
    te, ne = load_rt([rt, rt], "edt")
    assert np.isnan(te[0]) and ne[0] == 0


@pytest.mark.skipif(not all(p.exists() for p in _need), reason="sample files missing")
def test_airborne_with_repeated_files_is_unchanged():
    one = compute_airborne(*_need)
    many = compute_airborne([_need[0]] * 2, [_need[1]] * 3, _need[2], [_need[3]] * 2)
    assert np.allclose(one.dnt, many.dnt)
    assert (many.rating.value, many.c, many.ctr) == (one.rating.value, one.c, one.ctr)
    assert len(many.names["receiver"]) == 3 and (many.t_counts == 2).all()
