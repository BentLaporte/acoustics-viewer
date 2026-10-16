"""Installation noise in the viewer: level history with time window, dialog, building overview."""
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from calc.building import (AirborneSituation, InstallationSituation, Project, Room)  # noqa: E402
from calc.installation import Recording  # noqa: E402

S = Path(__file__).parent.parent / "samples"
L22, BG = S / "installatiegeluid_L22.SVL", S / "installatiegeluid_BG_L39.SVL"
RT = [S / "installatiegeluid_RT_L15.SVL", S / "installatiegeluid_RT_L16.SVL"]
pytestmark = pytest.mark.skipif(not all(p.exists() for p in [L22, BG, *RT]),
                                reason="installation noise sample files not present")
LE = chr(0x2264)


@pytest.fixture(scope="module")
def app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture()
def settings(tmp_path):
    from PySide6 import QtCore
    return QtCore.QSettings(str(tmp_path / "s.ini"), QtCore.QSettings.IniFormat)


def project(**kw) -> Project:
    rooms = [Room("Slaapkamer 1", [str(p) for p in RT], [str(BG)]), Room("Technische ruimte")]
    s = InstallationSituation("Slaapkamer 1", [Recording(L22)], comment="warmtepomp", **kw)
    return Project(name="Test", rooms=rooms, installation=[s])


def test_level_history_window(app):
    from gui.installation_dialog import LevelHistory
    from svl.parser import read_svl
    h = LevelHistory()
    seen = []
    h.window_changed.connect(lambda a, b: seen.append((a, b)))
    h.show_file(read_svl(L22), Recording(L22, 2, 8))
    assert (h.start.value(), h.end.value()) == (2, 8) and h.window() == (2, 8)
    assert h.region.getRegion() == (2, 8)
    h.end.setValue(10)                                    # to the end of the file = no end
    assert seen[-1] == (2, None) and h.window() == (2, None)
    h.region.setRegion((3.4, 6.6))                        # dragged: snapped to whole seconds
    h._region_done()
    assert seen[-1] == (3, 7)
    h.use_whole_file()
    assert seen[-1] == (0, None)
    h.show_file(None)
    assert not h.start.isEnabled()


def test_dialog_result_and_window(app, settings):
    from gui.installation_dialog import InstallationDialog
    p = project(requirement=44)
    dlg = InstallationDialog(p, settings, [], p.installation[0])
    assert dlg.name() == "installation in Slaapkamer 1 (warmtepomp)"
    assert dlg.table.rowCount() == 1 and dlg.table.item(0, 3).text() == "44.5"
    assert "LAeq,nT = 44 dB" in dlg.result.text() and "Complies" in dlg.result.text()
    dlg.history._set(2, 8)                                # the user drags the region
    assert dlg.recordings[0] == Recording(L22, 2, 8)
    assert dlg.table.item(0, 1).text() == "2-8 s" and dlg.table.item(0, 2).text() == "6 s"
    dlg.quantity.setCurrentIndex(dlg.quantity.findData("lafmax"))
    assert dlg.requirement.label.text() == f"LAFmax,nT {LE}"
    # LAFmax of seconds 2-8 is 45.94; 45.94 - 0.47 = 45.47 -> 45 dB, above the 44 dB required
    assert "LAFmax,nT = 45 dB" in dlg.result.text() and "Does not comply" in dlg.result.text()
    s = dlg.situation()
    assert (s.quantity, s.requirement, s.recordings) == ("lafmax", 44, [Recording(L22, 2, 8)])


def test_dialog_checks_the_input(app, settings, monkeypatch):
    from gui import installation_dialog as idlg
    warnings = []
    monkeypatch.setattr(idlg, "_warn", lambda parent, text: warnings.append(text))
    p = project()
    dlg = idlg.InstallationDialog(p, settings, ["installation in Slaapkamer 1 (warmtepomp)"],
                                  p.installation[0])
    dlg.method.setCurrentIndex(dlg.method.findData("positions"))
    dlg.accept()
    assert "exactly three files" in warnings[-1]
    dlg.method.setCurrentIndex(dlg.method.findData("integrated"))
    dlg.accept()
    assert "already a measurement" in warnings[-1]
    dlg.source.set_value("Slaapkamer 1")
    dlg.accept()
    assert "same" in warnings[-1]


def test_building_overview_with_installation(app, settings):
    from gui.building_page import BuildingPage
    page = BuildingPage(settings)
    page.set_project(project(requirement=40))
    t = page.ins_table
    assert t.rowCount() == 1
    assert [t.item(0, j).text() for j in (1, 2, 3)] == ["\u2192 Slaapkamer 1 (warmtepomp)", "44",
                                                       "LAeq,nT"]
    assert t.item(0, 4).text() == f"{LE} 40 dB" and t.item(0, 5).text().startswith("Does not comply")
    assert not page.sections["installation"].isHidden()
    assert page.sections["airborne"].isHidden() and page.sections["impact"].isHidden()
    assert page.meas_table.item(0, 1).text() == f"{LE} 40 dB"
    assert page.locate(0) == ("installation", 0)


def test_rooms_follow_installation_measurements(app, settings):
    from gui.building_page import BuildingPage
    page = BuildingPage(settings)
    p = project(source_room="Technische ruimte")
    p.airborne.append(AirborneSituation("Technische ruimte", "Slaapkamer 1"))
    page.set_project(p)
    assert page.locate(0) == ("airborne", 0) and page.locate(1) == ("installation", 0)
    assert page.users_of("Technische ruimte") == [
        "airborne Technische ruimte to Slaapkamer 1",
        "installation Technische ruimte to Slaapkamer 1 (warmtepomp)"]


def test_add_installation_measurement(app, settings, monkeypatch):
    from gui import building_page as bp
    page = bp.BuildingPage(settings)
    page.set_project(project())
    new = InstallationSituation("Slaapkamer 1", [Recording(L22, 0, 5)], comment="ventilatie",
                                quantity="lafmax")

    class FakeDialog:
        def __init__(self, project, settings, taken, situation=None, parent=None):
            FakeDialog.taken = taken

        def exec(self):
            return True

        def situation(self):
            return new

    monkeypatch.setattr(bp, "InstallationDialog", FakeDialog)
    page.add_measurement("installation")
    assert FakeDialog.taken == ["installation in Slaapkamer 1 (warmtepomp)"]
    assert page.project.installation[-1] is new and page.dirty
    assert page.ins_table.rowCount() == 2 and page.ins_table.item(1, 3).text() == "LAFmax,nT"
