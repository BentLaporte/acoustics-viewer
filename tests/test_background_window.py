"""Time windows on background files, the background-subtracted verdict of installation noise and
reverberation times taken from another room (Himpe project, Oct 2026)."""
import datetime as dt
import os
from pathlib import Path

import numpy as np
import pytest

from calc.building import (InstallationSituation, Evaluated, Project, Room, load_project,
                           rt_from_note, save_project, window_notes)
from calc.installation import InstallationResult, check_requirement
from calc.measurements import FileInfo, Recording, as_recordings, load_levels_info
from export.report_text import note_text
from svl.parser import ISO_SLICE, read_svl

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
S = Path(__file__).parent.parent / "samples"
BG, L22 = S / "installatiegeluid_BG_L39.SVL", S / "installatiegeluid_L22.SVL"
RT = [S / "installatiegeluid_RT_L15.SVL", S / "installatiegeluid_RT_L16.SVL"]
needs_samples = pytest.mark.skipif(not all(p.exists() for p in [BG, L22, *RT]),
                                   reason="installation noise sample files not present")


# ----------------------------------------------------------------------------- windows
def test_recording_spec_round_trip():
    r = Recording.parse("folder/L34.SVL@0-4")
    assert (r.start, r.end, r.window_text) == (0, 4, "0-4 s")
    assert Recording.parse(r.spec) == r
    assert Recording.parse("L34.SVL").spec == "L34.SVL"           # no window: just the path
    assert Recording.parse("L34.SVL@5-").end is None               # to the end of the file
    assert [x.path.name for x in as_recordings(["a.SVL", Recording(Path("b.SVL"), 1, 3)])] \
        == ["a.SVL", "b.SVL"]


@needs_samples
def test_a_window_on_a_level_file_uses_only_those_seconds():
    f = read_svl(BG)
    levels, infos = load_levels_info([f"{BG}@2-6"])
    assert levels == pytest.approx(f.leq_total(2, 6)[ISO_SLICE])
    assert infos[0].name == BG.name and infos[0].window == "2-6 s"
    _, whole = load_levels_info([str(BG)])
    assert whole[0].window == ""


def test_window_remarks_name_the_part_used():
    info = {"background": [FileInfo("L34.SVL", None, None, None, window="0-4 s")],
            "level": [FileInfo("L17.SVL", None, None, None, window="2-8 s")]}
    notes = window_notes(info)
    assert notes == ["L34.SVL: only 0-4 s used"]        # installation recordings: own table
    assert note_text(notes[0]) == "L34.SVL: enkel 0-4 s gebruikt"


def test_project_file_keeps_windows_and_rt_from(tmp_path):
    files = tmp_path / "Svanfiles"
    p = Project(name="P", background_files=[str(files / "L40.SVL@1-")])
    p.rooms = [Room("1.11", [str(files / "L9.SVL")], [str(files / "L34.SVL@0-4")],
                    rt_from="1.12 instructieruimte")]
    path = tmp_path / "project" / "p.json"
    path.parent.mkdir()
    save_project(p, path)
    text = path.read_text(encoding="utf-8")
    assert "../Svanfiles/L34.SVL@0-4" in text                # relative path, window kept
    q = load_project(path)
    assert Recording.parse(q.rooms[0].background_files[0]) == \
        Recording((files / "L34.SVL").resolve(), 0, 4)
    assert Recording.parse(q.background_files[0]).start == 1
    assert q.rooms[0].rt_from == "1.12 instructieruimte"


# ----------------------------------------------------------------------------- verdict
def result(level, background, k=0.38, quantity="laeq") -> InstallationResult:
    levels = np.array([level], float)
    return InstallationResult(
        quantity=quantity, method="integrated", recordings=[], levels=levels, durations=[10],
        level=level, background=background, margins=levels - background, t_thirds={},
        t20_used={}, t_octaves={}, k=k, lnt=level - k)


def test_a_failure_is_sure_when_it_stays_after_subtracting_the_background():
    # Himpe 1.06 + 1.07: 40.4 dB, background 37.3 dB -> at least 37 dB, limit 35 + 1
    r = result(40.44, 37.31)
    assert r.background_affected
    assert r.lnt_without_background == pytest.approx(37.17, abs=0.01)
    assert r.fails_anyway(35, tolerance=1)
    assert check_requirement(r, 35) == "fails"
    ev = Evaluated("installation", "x", "", "R", r, requirement=35, basis="laeq", tolerance=1)
    assert ev.check.status == "fails"
    assert ev.notes[-1] == "does not comply even with the background subtracted (at least 37 dB)"
    assert note_text(ev.notes[-1]) == \
        "voldoet ook na aftrek van het achtergrondgeluid niet (minstens 37 dB)"


def test_a_failure_stays_inconclusive_when_the_background_could_explain_it():
    below = result(37.0, 42.3)                       # Himpe 1.11: level under the background
    assert below.lnt_without_background is None
    assert check_requirement(below, 35) == "inconclusive"
    close = result(38.0, 36.5)                       # subtracted: 32.7 dB, could comply
    assert not close.fails_anyway(35)
    ev = Evaluated("installation", "x", "", "R", close, requirement=35, basis="laeq")
    assert ev.check.status == "inconclusive"
    # LAFmax: the maximum of the background is unknown, so no lower bound
    assert result(45.0, 30.0, quantity="lafmax").lnt_without_background is None


# ----------------------------------------------------------------------------- RT of another room
def test_rt_from_another_room_is_a_remark():
    assert note_text(rt_from_note("1.11 instructieruimte")) == \
        "nagalmtijd niet in deze ruimte gemeten; overgenomen van: 1.11 instructieruimte"


@needs_samples
def test_rt_from_another_room_in_the_evaluation_and_on_the_first_page(tmp_path):
    pytest.importorskip("reportlab")
    pypdf = pytest.importorskip("pypdf")
    from calc.building import evaluate_project
    from export.pdf_report import ReportOptions, build_pdf_report
    p = Project(name="Borrowed")
    p.rooms = [Room("1.06", [str(x) for x in RT], [f"{BG}@0-5"], rt_from="1.11 instructieruimte")]
    p.installation = [InstallationSituation("1.06", [Recording(L22)], requirement=30)]
    ev = evaluate_project(p)[0]
    assert ev.ok and ev.rt_from == "1.11 instructieruimte"
    assert rt_from_note("1.11 instructieruimte") in ev.notes
    assert f"{BG.name}: only 0-5 s used" in ev.notes
    out = build_pdf_report(p, [ev], tmp_path / "r.pdf",
                           ReportOptions(date=dt.date(2026, 10, 20), measurement_remarks=False))
    first = " ".join(pypdf.PdfReader(str(out)).pages[0].extract_text().split())
    assert "overgenomen van een andere ruimte: 1.06 (van 1.11 instructieruimte)" in first


# ----------------------------------------------------------------------------- viewer
@needs_samples
def test_background_window_dialog_and_row(tmp_path):
    pytest.importorskip("PySide6")
    pytest.importorskip("pyqtgraph")
    from PySide6 import QtCore, QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from gui.background_window import BackgroundRow, BackgroundWindowDialog
    dlg = BackgroundWindowDialog([str(BG)])
    assert dlg.list.count() == 1 and "whole file" in dlg.list.item(0).text()
    dlg.history._set(1, 4)                          # as if the region was dragged
    assert dlg.specs() == [f"{BG}@1-4"]
    assert "1-4 s" in dlg.list.item(0).text() and "LAeq of the window" in dlg.result.text()
    settings = QtCore.QSettings(str(tmp_path / "s.ini"), QtCore.QSettings.IniFormat)
    row = BackgroundRow("Background", settings)
    assert not row.window_button.isEnabled()        # nothing to window yet
    row.set_paths(dlg.specs())
    assert row.window_button.isEnabled() and row.paths() == [f"{BG}@1-4"]
    assert row.edit.text() == f"{BG.name} (1-4 s)"
