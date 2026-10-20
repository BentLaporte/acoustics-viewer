"""Seconds marked by the instrument (record flag 1) are left out, and reverberation time falls
back to T20 per band and file where T30 is missing (Bent's choices, Himpe project, Oct 2026)."""
import datetime as dt
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from calc import measurements
from calc.building import flagged_notes, seconds_text, t20_note
from calc.iso717 import BANDS
from calc.measurements import FileInfo, load_rt_fallback
from export.report_text import note_text
from svl.parser import SvlError, read_svl

S = Path(__file__).parent.parent / "samples"
SRC = S / "luchtgeluid_bron_L2.SVL"
needs_sample = pytest.mark.skipif(not SRC.exists(), reason="sample file missing")


# ----------------------------------------------------------------------------- flagged seconds
@needs_sample
def test_flagged_seconds_are_read_and_left_out(tmp_path):
    from helpers import make_flagged
    clean = read_svl(SRC)
    f = read_svl(make_flagged(SRC, tmp_path / "f.SVL", [0, 1, 4]))
    assert f.flagged_seconds == [0, 1, 4]
    assert len(f.seconds) == len(clean.seconds)                 # the history still shows all
    used = [s for i, s in enumerate(clean.seconds) if i not in (0, 1, 4)]
    expect = 10 * np.log10(np.mean([10 ** (s.leq_spectrum / 10) for s in used], axis=0))
    assert f.leq_total() == pytest.approx(expect, abs=0.01)
    assert not np.allclose(f.leq_total(), clean.leq_total(), atol=0.01)


@needs_sample
def test_a_file_with_every_second_flagged_is_refused(tmp_path):
    # without one unmarked second the alignment cannot be confirmed: refuse, do not guess
    from helpers import make_flagged
    n = len(read_svl(SRC).seconds)
    with pytest.raises(SvlError):
        read_svl(make_flagged(SRC, tmp_path / "all.SVL", range(n)))


def test_seconds_text_and_remarks():
    assert seconds_text([0, 1, 2, 5]) == "1-3, 6"
    assert seconds_text([4]) == "5"
    info = {"source": [FileInfo("L1.SVL", None, None, None, (0, 1, 2, 3, 4, 5))],
            "receiver": [FileInfo("L2.SVL", None, None, None)]}
    notes = flagged_notes(info)
    assert notes == ["L1.SVL: seconds 1-6 marked by the instrument, left out"]
    assert note_text(notes[0]) == \
        "L1.SVL: seconden 1-6 door het meettoestel gemarkeerd, niet gebruikt"


# ----------------------------------------------------------------------------- T30 else T20
class FakeRt:
    def __init__(self, t30, t20):
        self.v = {"t30": np.array(t30, float), "t20": np.array(t20, float)}
        self.device, self.measured_at = None, dt.datetime(2026, 10, 14)

    def at(self, bands, kind):
        return self.v[kind.lower()]


def test_t30_is_completed_by_t20_per_band_and_file(monkeypatch):
    n = len(BANDS)
    a = FakeRt([np.nan] + [1.0] * (n - 1), [0.8] + [0.9] * (n - 1))   # no T30 at 100 Hz
    b = FakeRt([1.2] * n, [0.7] * n)                                   # complete
    files = {"a.SVL": a, "b.SVL": b}
    monkeypatch.setattr(measurements, "read_rt", lambda p: files[Path(p).name])
    t, count, infos, used = load_rt_fallback(["a.SVL", "b.SVL"], "t30")
    assert t[0] == pytest.approx((0.8 + 1.2) / 2)          # T20 of a, T30 of b
    assert t[1] == pytest.approx((1.0 + 1.2) / 2)          # T30 wherever it exists
    assert count[0] == 2
    assert used == {100.0: ["a.SVL"]}
    assert t20_note(used) == "T20 used at 100 Hz (no T30)"
    # another evaluation range asked for: no fallback
    t, _, _, used = load_rt_fallback(["a.SVL"], "t20")
    assert used == {} and t[0] == pytest.approx(0.8)
