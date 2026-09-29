"""Checks svl.rt against the SvanPC++ table 'RT60 (SR)' for samples/L11.SVL."""
import re
from pathlib import Path

import numpy as np
import pytest

from svl.rt import read_rt

SAMPLES = Path(__file__).parent.parent / "samples"
SVL = SAMPLES / "L11.SVL"
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


def test_levels_match_csv():
    csv = SAMPLES / "L11.csv"
    if not csv.exists():
        pytest.skip("csv missing")
    body = csv.read_text()
    body = body[body.index("// buffer contents"):]
    parts = re.split(r"//rec\.(\d+)\.::", body)
    rows = []
    for k in range(1, len(parts) - 2, 2):        # skip last record (carries the RT table text)
        nums = [float(t) for t in re.findall(r"-?\d+\.\d+", parts[k + 1])][:34]
        rows.append(nums)
    rows = np.array(rows)
    r = read_rt(SVL)
    got = np.hstack([r.levels, r.broadband])[: len(rows)]
    # negative levels are stored as signed int16; all 646 x 34 values must agree
    assert np.abs(got - rows).max() < 0.006


def test_result_kind_validation():
    with pytest.raises(ValueError):
        read_rt(SVL).result("t60")
