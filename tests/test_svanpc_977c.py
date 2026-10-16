"""The SV 977C files compared with SvanPC++ (values exported to Excel by the project owner).

  * 977C_L1.SVL = "L1.SVL": SvanPC++ "Total results", 1/3 Oct LZeq (SR) [dB], 10 s,
    0.8 Hz ... 20 kHz, started 28/09/2026 11:08:35; and its "Header information"
    (Device type SVAN 977C, serial 98053, internal software version 2.23.1, logger step 1 s,
    10 logger records, 1/3 octave in logger: Leq, Lmin, Lmax; profiles A fast, A slow, Z fast
    with LApeak/LAFmax/LAFmin/LAeq, LApeak/LASmax/LASmin/LAeq, LZpeak/LZFmax/LZFmin/LZeq).
  * 977C_RT_L34.SVL = "L34.SVL": SvanPC++ "RT60 (SR)" table.
Skipped when the sample files are not present.
"""
from pathlib import Path

import numpy as np
import pytest

from svl.parser import read_svl
from svl.rt import read_rt

SAMPLES = Path(__file__).parent.parent / "samples"
LEVEL, RT = SAMPLES / "977C_L1.SVL", SAMPLES / "977C_RT_L34.SVL"

# SvanPC++ "Total results": 1/3 Oct LZeq (SR) [dB], 0.8 Hz ... 20 kHz (2 decimals)
SVANPC_LZEQ = np.array([
    46.81, 53.84, 52.17, 53.86, 48.3, 49.79, 50.76, 46.92, 47.88, 45.06, 46.33, 42.55, 42.08,
    46.99, 47.36, 53.69, 62.64, 76.42, 78.61, 78.53, 87.46, 89.31, 90.64, 90.92, 86.57, 78.91,
    80.04, 79.67, 85.96, 86.94, 84.11, 80.74, 82.17, 82.81, 83.98, 83.41, 83.56, 82.03, 82.44,
    82.76, 82.03, 79.93, 72.27, 63.61, 61.63,
])

# SvanPC++ RT60 (SR): Freq, EDT, RT20, RT30 [s] (3 decimals); nan = ***
SVANPC_RT = """
50 0.461 1.118 1.273
63 0.501 0.62 0.627
80 1.208 0.74 0.727
100 0.939 0.622 0.644
125 0.641 0.922 0.735
160 0.735 0.594 0.503
200 0.137 0.822 0.708
250 0.537 0.662 0.709
315 1.244 0.511 0.528
400 1.472 0.876 0.803
500 1.469 0.695 0.679
630 0.602 0.663 0.683
800 1.231 0.622 0.597
1000 0.585 0.702 0.656
1250 0.724 0.549 0.574
1600 0.63 0.53 0.568
2000 0.596 0.615 0.62
2500 0.651 0.557 0.581
3150 0.674 0.601 0.617
4000 0.593 0.581 0.557
5000 0.495 0.539 0.555
Total_A 0.608 0.558 0.586
Total_C 0.674 0.516 0.594
Total_Z 0.686 0.511 0.599
"""


def rt_rows():
    rows = [ln.split() for ln in SVANPC_RT.strip().splitlines()]
    bands = [r for r in rows if not r[0].startswith("Total_")]
    totals = [r for r in rows if r[0].startswith("Total_")]
    to = lambda r: [float(x) for x in r[1:]]                                   # noqa: E731
    return (np.array([float(r[0]) for r in bands]), np.array([to(r) for r in bands]),
            np.array([to(r) for r in totals]))


@pytest.mark.skipif(not LEVEL.exists(), reason="977C level sample missing")
def test_level_file_matches_svanpc_lzeq_and_header():
    s = read_svl(LEVEL)
    assert s.name == "L1" and s.duration_s == 10                    # header: 10 logger records
    d = s.device                                                     # header: SVAN 977C, 98053, 2.23
    assert (d.label, d.serial, d.firmware, d.class_code) == ("SV 977C", 98053, 223, 21)
    assert len(SVANPC_LZEQ) == 45
    # the 10 s LZeq of SvanPC++ against the energy average of our decoded 1 s spectra
    assert np.abs(s.leq_total() - SVANPC_LZEQ).max() < 0.011
    # and against the whole-file spectrum the instrument stored itself (exactly SvanPC++)
    assert np.abs(s.stored_total - SVANPC_LZEQ).max() < 0.0051


@pytest.mark.skipif(not RT.exists(), reason="977C reverberation sample missing")
def test_reverberation_file_matches_svanpc_table_exactly():
    r = read_rt(RT)
    assert r.name == "L34" and r.device.label == "SV 977C"
    hz, rows, totals = rt_rows()
    assert np.array_equal(r.rt_hz, hz)
    for col, arr in enumerate((r.edt, r.t20, r.t30)):
        np.testing.assert_allclose(arr, rows[:, col], atol=1e-9)
    for col, arr in enumerate((r.total_edt, r.total_t20, r.total_t30)):     # Total A, C, Z
        np.testing.assert_allclose(arr, totals[:, col], atol=1e-9)
    # SvanPC++'s RTResult column equals RT30 in every row, as on the 977D
    np.testing.assert_allclose(r.at(hz, "t30"), rows[:, 2], atol=1e-9)


@pytest.mark.skipif(not LEVEL.exists(), reason="977C level sample missing")
def test_spectra_and_profiles_follow_the_header():
    """Header: 1/3 octave in logger = Leq, Lmin, Lmax; three profiles x (peak, max, min, eq)."""
    s = read_svl(LEVEL)
    tot = lambda sp: 10 * np.log10(np.sum(10 ** (sp / 10)))                     # noqa: E731
    for sec in s.seconds:
        assert tot(sec.lmax_spectrum) >= tot(sec.leq_spectrum) >= tot(sec.lmin_spectrum)
        p = sec.profiles
        assert p.shape == (3, 4)
        assert p[0, 0] == p[1, 0] and p[0, 3] == p[1, 3]                        # both profiles A
        # last column = Leq of the profile: LAeq, LAeq, LZeq of the Leq spectrum's broadband values
        la, lc, lz = sec.leq_broadband
        assert abs(p[0, 3] - la) < 0.011 and abs(p[1, 3] - la) < 0.011 and abs(p[2, 3] - lz) < 0.011
        assert np.all(p[:, 1] >= p[:, 2])                                        # max >= min
