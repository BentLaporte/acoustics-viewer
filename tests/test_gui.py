"""Smoke tests of the viewer with the sample files (offscreen, skipped if unavailable)."""
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

S = Path(__file__).parent.parent / "samples"
AIR = {"source": S / "A_L2.SVL", "receiver": S / "B_L2.SVL",
       "background": S / "C_L20.SVL", "rt": S / "B_L11.SVL"}
IMP = {"tapping": S / "B_L4.SVL", "background": S / "C_L20.SVL", "rt": S / "B_L11.SVL"}
pytestmark = pytest.mark.skipif(
    not all(p.exists() for p in {**AIR, **IMP}.values()), reason="sample files missing")


@pytest.fixture(scope="module")
def app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture()
def settings(tmp_path):
    from PySide6 import QtCore
    return QtCore.QSettings(str(tmp_path / "s.ini"), QtCore.QSettings.IniFormat)


def test_airborne_page(app, settings):
    from gui.airborne_page import AirbornePage
    w = AirbornePage(settings)
    w.load(AIR)
    assert w.result is not None and len(w.result.bands) == 16
    assert w.table.item(0, 0).text() == "100"
    assert w.table.item(15, 9).text() == "67.5"                 # DnT at 3150 Hz
    x, y = w.rating_plot.c_ref.getData()
    assert len(x) == 16 and y[7] == 54                           # shifted curve at 500 Hz
    text = w.summary.text()
    assert "= 54" in text and "(\u22121; \u22124)" in text
    assert w.table.item(4, 10).text() == "47"                    # 45 + 2 at 250 Hz
    assert w.table.item(4, 11).text() == "3.6"                   # deviation at 250 Hz
    w.show_hover(7)
    assert w.hover.text().strip().startswith("500 Hz") and "ref 54" in w.hover.text()


def test_airborne_missing_rt(app, settings):
    from gui.airborne_page import AirbornePage
    w = AirbornePage(settings)
    w.load(AIR)
    w.rt_kind.setCurrentIndex(w.rt_kind.findData("edt"))        # EDT missing at 100 Hz
    assert w.result.rating is None
    assert "Rating not possible" in w.summary.text() and "100" in w.summary.text()
    assert w.table.item(0, 10).text() == "-"


def test_impact_page(app, settings):
    from gui.impact_page import ImpactPage
    w = ImpactPage(settings)
    w.load(IMP)
    assert w.result is not None and w.result.rating.value == 44
    assert "= 44 (\u22121) dB" in w.summary.text() and "C<sub>I</sub> = 43 dB" in w.summary.text()
    x, y = w.rating_plot.c_ref.getData()
    assert y[7] == 44                                             # 60 - 16 at 500 Hz
    assert w.table.item(3, 9).text() == "2.2"                     # deviation at 200 Hz
    assert w.table.item(0, 9).text() == "-"                       # no deviation at 100 Hz
    # bars start at the curve and end at the measured value (deviation above the curve)
    bars = w.rating_plot.bars.opts
    assert bars["y0"][0] == 46 and abs(bars["height"][0] - 2.2) < 0.05


def test_impact_missing_rt(app, settings):
    from gui.impact_page import ImpactPage
    w = ImpactPage(settings)
    w.load(IMP)
    w.rt_kind.setCurrentIndex(w.rt_kind.findData("edt"))
    assert w.result.rating is None and "Rating not possible" in w.summary.text()


def test_main_window_shares_background_and_rt(app, monkeypatch, tmp_path):
    from PySide6 import QtCore
    import gui.app as ga
    real = QtCore.QSettings                      # keep the real class before patching
    monkeypatch.setattr(ga.QtCore, "QSettings",
                        lambda *a, **k: real(str(tmp_path / "m.ini"), real.IniFormat))
    w = ga.MainWindow()
    w.airborne.rows["background"].set_path(str(AIR["background"]))
    assert w.impact.rows["background"].path() == str(AIR["background"])   # copied over
    w.impact.rows["rt"].set_path(str(IMP["rt"]))
    assert w.airborne.rows["rt"].path() == str(IMP["rt"])
    # an already filled row is never overwritten
    other = str(S / "B_L2.SVL")
    w.impact.rows["background"].set_path(other)
    assert w.airborne.rows["background"].path() == str(AIR["background"])
    w.load({**AIR, **IMP})
    assert w.airborne.result.rating.value == 54 and w.impact.result.rating.value == 44


def test_bad_file_does_not_crash(app, settings, monkeypatch, tmp_path):
    from PySide6 import QtWidgets
    from gui.impact_page import ImpactPage
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a, **k: None)
    bad = tmp_path / "x.SVL"
    bad.write_bytes(b"not an svl file")
    w = ImpactPage(settings)
    w.load({**IMP, "tapping": bad})
    assert w.result is None


def test_several_files_are_averaged_and_explained(app, settings):
    from gui.impact_page import ImpactPage
    w = ImpactPage(settings)
    w.load({"tapping": [IMP["tapping"], IMP["tapping"], IMP["tapping"]],
            "background": IMP["background"], "rt": [IMP["rt"], IMP["rt"]]})
    assert w.rows["tapping"].edit.text().startswith("3 files: B_L4.SVL")
    assert w.result.rating.value == 44                          # identical files: same result
    assert "tapping machine positions: 3" in w.summary.text()
    assert "reverberation time decays: 2" in w.summary.text()
    assert "3 files" in w.status_text(w.result)


def test_file_row_add_and_clear(app, settings, monkeypatch):
    from PySide6 import QtWidgets
    from gui.widgets import FileRow
    row = FileRow("x", settings)
    row.set_paths([str(S / "A_L2.SVL")])
    monkeypatch.setattr(QtWidgets.QFileDialog, "getOpenFileNames",
                        lambda *a, **k: ([str(S / "B_L2.SVL"), str(S / "A_L2.SVL")], ""))
    row.browse(add=True)                                        # duplicates are skipped
    assert [Path(p).name for p in row.paths()] == ["A_L2.SVL", "B_L2.SVL"]
    row.browse(add=False)                                       # replaces
    assert [Path(p).name for p in row.paths()] == ["B_L2.SVL", "A_L2.SVL"]
    row.clear_button.click()
    assert row.paths() == [] and row.path() == ""
