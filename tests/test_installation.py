"""Installation noise (ISO 10052 / NBN S 01-400-1): formulas, LAeq / LAFmax from SVL files, the
calculation from files and the command line.

The sample file installatiegeluid_L22.SVL (SV 977D, 10 s, 14/10/2026 16:22:05) is compared with
SvanPC++ "Main results for sound", profile P1 (A, Fast), and its 1/3 Oct Leq (Total A 44.5).
Sample tests skip when the file is not present.
"""
from pathlib import Path

import numpy as np
import pytest

from calc import cli
from calc.installation import Recording, check_requirement, compute_installation
from calc.iso10052 import octave_rt, reverberation_index, round_db, standardized_level
from helpers import make_variant
from svl.parser import Second, SvlError, SvlFile, read_svl

SAMPLES = Path(__file__).parent.parent / "samples"
L22 = SAMPLES / "installatiegeluid_L22.SVL"
RT = [SAMPLES / "installatiegeluid_RT_L15.SVL", SAMPLES / "installatiegeluid_RT_L16.SVL"]
BG = SAMPLES / "installatiegeluid_BG_L39.SVL"
needs_samples = pytest.mark.skipif(not all(p.exists() for p in [L22, BG, *RT]),
                                   reason="installation noise sample files not present")


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


# --- more formulas -----------------------------------------------------------------------------

def test_octave_rt_is_the_arithmetic_mean_of_the_thirds():
    assert octave_rt([0.4, 0.5, 0.9]) == pytest.approx(0.6)
    with pytest.raises(ValueError):
        octave_rt([0.4, 0.5])


@pytest.mark.parametrize("x, expected", [(30.49, 30), (30.5, 31), (30.51, 31), (44.04, 44),
                                         (45.62, 46), (-0.5, 0)])
def test_round_db_whole_db_halves_up(x, expected):
    assert round_db(x) == expected


@pytest.mark.parametrize("spec, path, start, end", [
    ("a.SVL", "a.SVL", 0, None),
    ("a.SVL@5-35", "a.SVL", 5, 35),
    ("a.SVL@5-", "a.SVL", 5, None),
    (r"C:\meting@kantoor\a.SVL", r"C:\meting@kantoor\a.SVL", 0, None),   # '@' in a folder name
])
def test_recording_parse(spec, path, start, end):
    r = Recording.parse(spec)
    assert (r.path, r.start, r.end) == (Path(path), start, end)


# --- calculation from the sample files ---------------------------------------------------------

@needs_samples
def test_laeq_nt_from_samples():
    r = compute_installation([L22], RT, BG)
    assert r.levels[0] == pytest.approx(44.511, abs=1e-3)
    # octave T: arithmetic mean of the thirds, mean of the two files per third, T20 where T30 is
    # missing (400, 500, 630 Hz in both files): 500 Hz = (0.4435 + 0.468 + 0.425) / 3
    assert r.t_octaves[500] == pytest.approx(0.4455, abs=1e-4)
    assert sorted(r.t20_used) == [400, 500, 630]
    assert r.k == pytest.approx(0.4732, abs=1e-4)
    assert r.lnt == pytest.approx(44.511 - 0.4732, abs=1e-3)
    assert r.value == 44
    assert r.background == pytest.approx(33.0, abs=0.01)
    assert r.margins[0] == pytest.approx(11.5, abs=0.01) and not r.background_affected
    assert any("integrated method" in n for n in r.notes)
    assert any("T20 used" in n for n in r.notes)


@needs_samples
def test_lafmax_nt_and_time_window_from_samples():
    r = compute_installation([L22], RT, BG, quantity="lafmax")
    assert r.levels[0] == pytest.approx(46.09) and r.value == 46     # 46.09 - 0.47 = 45.62
    w = compute_installation([f"{L22}@2-8"], RT, quantity="lafmax")
    assert w.durations == [6] and w.levels[0] == pytest.approx(45.94)
    assert any("not checked" in n for n in w.notes)


@needs_samples
def test_position_method_needs_three_measurements_and_averages_them(tmp_path):
    up = make_variant(L22, tmp_path / "up.SVL", 3.0)
    down = make_variant(L22, tmp_path / "down.SVL", -3.0)
    r = compute_installation([L22, up, down], RT, method="positions")
    # 10 lg((10^4.4511 + 10^4.7511 + 10^4.1511) / 3) = 45.176
    assert r.level == pytest.approx(45.176, abs=1e-3)
    assert not any("integrated method" in n for n in r.notes)
    with pytest.raises(ValueError, match="needs 3"):
        compute_installation([L22], RT, method="positions")


@needs_samples
def test_background_check_and_requirement(tmp_path):
    r = compute_installation([L22], RT, BG)                        # 44 dB, 11.5 dB above Lb
    assert check_requirement(r, None) == "none"
    assert check_requirement(r, 44) == "complies"
    assert check_requirement(r, 43) == "fails"
    quiet = make_variant(L22, tmp_path / "quiet.SVL", -8.0)         # 36.5 dB, 3.5 dB above Lb
    q = compute_installation([quiet], RT, BG)
    assert q.background_affected and any("overestimated" in n for n in q.notes)
    assert q.value == 36                                           # no correction applied
    assert check_requirement(q, 36) == "complies"                  # a pass stays reliable
    assert check_requirement(q, 35) == "inconclusive"              # a failure may be the background


# --- command line ------------------------------------------------------------------------------

def run(capsys, *argv):
    code = cli.main([str(a) for a in argv])
    out = capsys.readouterr()
    return code, out.out, out.err


@needs_samples
def test_cli_text_json_csv(capsys):
    base = ["installation", "--level", L22, "--rt", *RT, "--background", BG]
    code, out, _ = run(capsys, *base, "--requirement", 30)
    assert code == 0 and "LAeq,nT = 44 dB" in out and "fails (-14 dB)" in out
    code, out, _ = run(capsys, *base, "--quantity", "lafmax", "--format", "json")
    import json
    d = json.loads(out)
    assert d["kind"] == "installation" and d["result"]["quantity"] == "LAFmax,nT"
    assert d["result"]["single_number_db"] == 46
    assert d["reverberation"]["t20_instead_of_t30_hz"] == [400, 500, 630]
    assert d["recordings"][0]["file"] == L22.name                  # file name only, no folder
    code, out, _ = run(capsys, *base, "--format", "csv")
    assert out.splitlines()[0].startswith("file,start_s,end_s")


@needs_samples
def test_cli_exit_status(capsys):
    code, _, err = run(capsys, "installation", "--level", f"{L22}@2-80", "--rt", *RT)
    assert code == 2 and "outside the measurement" in err and str(SAMPLES) not in err
    code, _, _ = run(capsys, "installation", "--level", L22, "--rt", *RT, "--requirement", 30,
                     "--strict")
    assert code == 1
