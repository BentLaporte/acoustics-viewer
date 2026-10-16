"""Checks svl.rt against the SvanPC++ table 'RT60 (SR)' for samples/ontvangstruimte_RT_L11.SVL.

(The level history was also compared value-for-value with a SvanPC++ CSV export once,
when the reader was written; that one-off check was retired together with the CSV.)"""
from pathlib import Path

import numpy as np
import pytest

from svl.rt import read_rt

SAMPLES = Path(__file__).parent.parent / "samples"
SVL = SAMPLES / "ontvangstruimte_RT_L11.SVL"
pytestmark = pytest.mark.skipif(not SVL.exists(), reason="sample file missing")

# Freq, EDT, RT20, RT30 as pasted from SvanPC++ (nan = ***)
NAN = float("nan")
SVANPC = """
50 3.737 3.126 2.987
63 1.474 3.076 2.843
80 1.947 2.251 2.471
100 *** 2.514 2.547
125 0.194 1.421 2.012
160 0.609 2.638 2.475
200 1.138 2.059 3.105
250 1.226 1.848 1.667
315 1.117 1.373 1.353
400 1.299 1.145 1.147
500 1.580 1.171 1.312
630 0.628 1.237 1.145
800 0.982 1.082 0.977
1000 1.078 1.080 1.012
1250 1.429 0.914 0.951
1600 0.816 0.724 0.815
2000 0.726 0.760 0.778
2500 0.494 0.683 0.718
3150 0.758 0.791 0.740
4000 0.519 0.587 0.615
5000 0.511 0.548 0.572
"""
TOTALS = {"A": (0.868, 1.149, 1.526), "C": (1.617, 2.115, 2.351), "Z": (1.632, 2.105, 2.365)}


def table():
    rows = [[NAN if t == "***" else float(t) for t in ln.split()]
            for ln in SVANPC.strip().splitlines()]
    return np.array(rows)


def test_rt_table_matches_svanpc():
    r = read_rt(SVL)
    t = table()
    np.testing.assert_allclose(r.rt_hz, t[:, 0])
    for col, arr in ((1, r.edt), (2, r.t20), (3, r.t30)):
        np.testing.assert_allclose(arr, t[:, col], atol=1e-9, equal_nan=True)


def test_totals_match_svanpc():
    r = read_rt(SVL)
    np.testing.assert_allclose(r.total_edt, [v[0] for v in TOTALS.values()])
    np.testing.assert_allclose(r.total_t20, [v[1] for v in TOTALS.values()])
    np.testing.assert_allclose(r.total_t30, [v[2] for v in TOTALS.values()])


def test_at_iso_bands():
    r = read_rt(SVL)
    bands = [100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600,
             2000, 2500, 3150]
    t30 = r.at(bands, "t30")
    assert t30[0] == pytest.approx(2.547) and t30[-1] == pytest.approx(0.740)
    assert not np.isnan(t30).any()


def test_result_kind_validation():
    with pytest.raises(ValueError):
        read_rt(SVL).result("t60")


def test_rt_file_reports_its_instrument():
    r = read_rt(SVL)
    assert r.device.label == "SV 977D" and r.device.serial == 156226


# ------------------------------------------------------------------ SV 977C reverberation file
RT_C = SAMPLES / "977C_RT_L34.SVL"
needs_rt_c = pytest.mark.skipif(not RT_C.exists(), reason="977C reverberation sample missing")


@needs_rt_c
def test_977c_rt_file_structure():
    """Structure of the 977C reverberation file (values: tests/test_svanpc_977c.py)."""
    r = read_rt(RT_C)
    assert r.device.label == "SV 977C" and r.device.serial == 98053
    assert r.levels.shape == (380, 31) and r.broadband.shape == (380, 3)
    assert r.band_hz[0] == 20 and r.band_hz[-1] == 20000
    assert r.levels.min() > -30 and r.levels.max() < 120                 # no misaligned words
    # the level history is a clean decay: loud while the source runs, then falling
    z = r.broadband[:, 2]
    assert z[:20].min() > 100 and z.min() < 45                           # source off after ~5 s
    assert np.all(np.diff(r.time_s) > 0) and r.time_s[1] == pytest.approx(0.02)
    # the stored table has the 21 bands 50 Hz - 5 kHz plus the totals A, C, Z, like the 977D
    assert list(r.rt_hz[[0, -1]]) == [50, 5000] and len(r.rt_hz) == 21
    assert len(r.total_t30) == 3 and not np.isnan(r.total_t30).any()
    for arr in (r.t20, r.t30):
        assert np.all((arr > 0.1) & (arr < 10))                          # plausible seconds
    bands = [100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150]
    t30 = r.at(bands, "t30")
    assert not np.isnan(t30).any() and 0.4 < t30.mean() < 1.0


@needs_rt_c
def test_977c_rt_values_as_decoded_today():
    """A few values of the table, which equals the SvanPC++ one (tests/test_svanpc_977c.py)."""
    r = read_rt(RT_C)
    row = {float(f): (e, a, b) for f, e, a, b in zip(r.rt_hz, r.edt, r.t20, r.t30)}
    assert row[50.0] == pytest.approx((0.461, 1.118, 1.273))
    assert r.total_t30 == pytest.approx([0.586, 0.594, 0.599])
    assert r.t30[0] == pytest.approx(1.273) and r.t20[0] == pytest.approx(1.118)


def test_level_files_are_not_accepted_as_reverberation_files():
    from svl.parser import SvlError
    for name in ("luchtgeluid_bron_L2.SVL", "977C_L1.SVL"):
        if (SAMPLES / name).exists():
            with pytest.raises(SvlError, match=name):
                read_rt(SAMPLES / name)
