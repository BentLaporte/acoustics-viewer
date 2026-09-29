"""Worked examples from the standards (Annex C, informative), one-third-octave bands.

Airborne: ISO 717-1, Annex C, Table C.1 (Rw = 30 dB, C = -2, Ctr = -3).
Impact:   EN ISO 717-2:2021, Annex C, Table C.1 (bare heavy floor and floor covering).

Numbers were typed in from screenshots of the standards supplied by the project owner.
Not covered: octave-band data (717-2 Table C.3), the floor-covering improvement
(717-2 Table C.2) and the enlarged frequency range examples (717-1 Table C.2).
"""
import numpy as np
import pytest

from calc.iso717 import (BANDS, SPECTRUM_1_PINK, SPECTRUM_2_TRAFFIC, adaptation_term,
                         airborne_summary, impact_adaptation_term, rate_airborne,
                         rate_impact)

NAN = 0.0   # a dash ("-") in the standard's tables means no unfavourable deviation


def test_bands_are_the_tables_frequencies():
    assert list(BANDS) == [100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250,
                           1600, 2000, 2500, 3150]


# ------------------------------------------------------------------ ISO 717-1 Table C.1
R = np.array([20.4, 16.3, 17.7, 22.6, 22.4, 22.7, 24.8, 26.6, 28.0, 30.5, 31.8, 32.5,
              33.4, 33.0, 31.0, 25.5])
R_REF = np.array([11, 14, 17, 20, 23, 26, 29, 30, 31, 32, 33, 34, 34, 34, 34, 34])
R_DEV = np.array([0, 0, 0, 0, 0.6, 3.3, 4.2, 3.4, 3.0, 1.5, 1.2, 1.5, 0.6, 1.0, 3.0, 8.5])


def test_airborne_rw_example():
    r = rate_airborne(R)
    assert r.shift == -22 and r.value == 30                       # Rw = 52 dB - 22 dB
    assert np.array_equal(r.curve, R_REF)                         # reference values shifted
    assert np.allclose(r.deviations, R_DEV, atol=1e-9)            # unfavourable deviations
    assert r.unfavourable_sum == pytest.approx(31.8)              # sum = 31.8 < 32


def test_airborne_adaptation_terms_example():
    x_a1 = -10 * np.log10(np.sum(10 ** ((SPECTRUM_1_PINK - R) / 10)))
    x_a2 = -10 * np.log10(np.sum(10 ** ((SPECTRUM_2_TRAFFIC - R) / 10)))
    assert x_a1 == pytest.approx(28.308, abs=1e-3)                # "28,308..."
    assert x_a2 == pytest.approx(26.859, abs=1e-3)                # "26,859..."
    assert np.sum(10 ** ((SPECTRUM_1_PINK - R) / 10)) == pytest.approx(147.6199e-5, rel=1e-5)
    assert np.sum(10 ** ((SPECTRUM_2_TRAFFIC - R) / 10)) == pytest.approx(206.0636e-5, rel=1e-5)
    assert adaptation_term(R, SPECTRUM_1_PINK, 30) == -2          # C  = 28 dB - 30 dB
    assert adaptation_term(R, SPECTRUM_2_TRAFFIC, 30) == -3       # Ctr = 27 dB - 30 dB
    s = airborne_summary(R)
    assert (s["w"], s["C"], s["Ctr"]) == (30, -2, -3)             # Rw(C;Ctr) = 30(-2;-3)


# ----------------------------------------------------- ISO 717-2 Table C.1, bare heavy floor
LN_BARE = np.array([62.1, 63.2, 63.5, 66.2, 68.5, 70.0, 71.7, 73.1, 73.8, 73.5, 73.8, 73.3,
                    73.1, 73.0, 72.4, 71.2])
BARE_REF = np.array([81, 81, 81, 81, 81, 81, 80, 79, 78, 77, 76, 73, 70, 67, 64, 61])
BARE_DEV = np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.3, 3.1, 6.0, 8.4, 10.2])

# ------------------------------------------ ISO 717-2 Table C.1, with floor covering
LN_COV = np.array([59.1, 59.5, 61.6, 63.2, 65.3, 66.5, 67.7, 67.0, 67.1, 66.5, 66.1, 62.5,
                   57.9, 52.7, 47.0, 48.0])
COV_REF = np.array([66, 66, 66, 66, 66, 66, 65, 64, 63, 62, 61, 58, 55, 52, 49, 46])
COV_DEV = np.array([0, 0, 0, 0, 0, 0.5, 2.7, 3.0, 4.1, 4.5, 5.1, 4.5, 2.9, 0.7, 0, 2.0])


def _lsum(v):
    return 10 * np.log10(np.sum(10 ** (np.asarray(v) / 10)))


@pytest.mark.parametrize("ln, ref, dev, total, value", [
    (LN_BARE, BARE_REF, BARE_DEV, 28.0, 79),
    (LN_COV, COV_REF, COV_DEV, 30.0, 64),
])
def test_impact_rating_examples(ln, ref, dev, total, value):
    r = rate_impact(ln)
    assert r.value == value                                        # Ln,w
    assert np.array_equal(r.curve, ref)                            # reference values shifted
    assert np.allclose(r.deviations, dev, atol=1e-9)               # unfavourable deviations
    assert r.unfavourable_sum == pytest.approx(total)              # 28,0 / 30,0 < 32,0


def test_impact_ci_floor_covering_example():
    # "Ln,sum = 76,059 3... = 76 dB, CI = 76 - 15 - 64 = -3 dB"
    assert impact_adaptation_term(LN_COV, 64) == -3


# --- DECISION: frequency range of the sum -------------------------------------------
# Clause A.2.1 of EN ISO 717-2:2021 says the values are summed over 100 - 2500 Hz (15
# bands). impact_adaptation_term follows that clause (decision of the project owner).
# The informative worked example in Annex C, however, gives Ln,sum values that only come
# out when 3150 Hz is included as well (16 bands):
#   floor covering: 15 bands 76.0525, 16 bands 76.0593 (example: 76,059 3...)
#   bare floor:     15 bands 83.2613, 16 bands 83.5234 (example: 83,523 8...)
# The gap (0.26 dB for the bare floor) is far larger than rounding of the printed 0.1 dB
# values could cause (at most about 0.05 dB), so the example appears to have been
# calculated over all 16 rows. For the bare floor the rounded sum changes (83 vs 84) and
# so does CI (-11 with 100-2500 Hz, -10 in the example).
# Consequence when comparing with other software: a program that sums 100-3150 Hz can
# differ by 1 dB in CI for spectra with a high level at 3150 Hz.
def test_impact_annex_c_sums_include_3150_hz():
    assert _lsum(LN_COV) == pytest.approx(76.0593, abs=1e-4)
    assert _lsum(LN_BARE) == pytest.approx(83.5238, abs=5e-4)
    assert _lsum(LN_COV[:15]) == pytest.approx(76.0525, abs=1e-4)
    assert _lsum(LN_BARE[:15]) == pytest.approx(83.2613, abs=1e-4)


def test_impact_ci_bare_floor_uses_100_to_2500_hz():
    assert impact_adaptation_term(LN_BARE, 79) == -11              # 83 - 15 - 79 (A.2.1)
    # the Annex C figure of -10 is what summing 100-3150 Hz gives:
    assert round(_lsum(LN_BARE)) - 15 - 79 == -10
