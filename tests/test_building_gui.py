"""Building page: setup tables, overview, curves, visibility, saving (offscreen)."""
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from calc.building import (AirborneSituation, ImpactSituation, Project, Room)  # noqa: E402
from helpers import make_variant  # noqa: E402

S = Path(__file__).parent.parent / "samples"
NEED = ["A_L2.SVL", "B_L2.SVL", "B_L4.SVL", "C_L20.SVL", "B_L11.SVL"]
pytestmark = pytest.mark.skipif(not all((S / n).exists() for n in NEED),
                                reason="sample files missing")


@pytest.fixture(scope="module")
def app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture()
def settings(tmp_path):
    from PySide6 import QtCore
    return QtCore.QSettings(str(tmp_path / "s.ini"), QtCore.QSettings.IniFormat)


def project(tmp_path) -> Project:
    quiet = make_variant(S / "B_L2.SVL", tmp_path / "C_recv.SVL", -3.0)
    f = lambda n: str(S / n)                                          # noqa: E731
    p = Project(name="Demo", background_files=[f("C_L20.SVL")])
    p.rooms = [Room("A"), Room("B", [f("B_L11.SVL")]), Room("C", [f("B_L11.SVL")])]
    p.airborne = [AirborneSituation("A", "B", [f("A_L2.SVL")], [f("B_L2.SVL")]),
                  AirborneSituation("A", "C", [f("A_L2.SVL")], [str(quiet)], "louder speaker"),
                  AirborneSituation("A", "B", [f("A_L2.SVL")], [f("nope.SVL")], "broken")]
    p.impact = [ImpactSituation("B", [f("B_L4.SVL")], "A", "carpet")]
    return p


def test_overview_tables_and_charts(app, settings, tmp_path):
    from gui.building_page import BuildingPage
    page = BuildingPage(settings)
    page.set_project(project(tmp_path))
    at, it = page.air_table, page.imp_table
    assert at.rowCount() == 3 and it.rowCount() == 1
    assert [at.item(i, 1).text() for i in range(3)] == [
        "A \u2192 B", "A \u2192 C (louder speaker)", "A \u2192 B (broken)"]
    assert at.item(0, 2).text() == "54" and at.item(0, 3).text() == "\u22121"      # DnT,w, C
    assert at.item(0, 4).text() == "\u22124"                                        # Ctr
    assert int(at.item(1, 2).text()) > 54                                           # quieter receiver
    assert at.item(2, 2).text() == "-" and "file not found: nope.SVL" in at.item(2, 7).text()
    assert it.item(0, 1).text() == "A \u2192 B (carpet)"
    assert it.item(0, 2).text() == "44" and it.item(0, 3).text() == "\u22121"       # L'nT,w, C_I
    assert at.item(0, 1).toolTip().startswith("airborne A to B")                    # generated name
    # charts hold the two good airborne curves (the broken one has no curve)
    assert len(page.air_curves.legend.items) == 2
    assert page.air_curves.table.columnCount() == 3 and page.air_curves.table.rowCount() == 16
    assert page.air_curves.table.item(15, 1).text() == "67.5"                        # DnT 3150 Hz
    assert page.air_curves.table.horizontalHeaderItem(2).toolTip() == "A \u2192 C (louder speaker)"
    assert len(page.imp_curves.legend.items) == 1


def test_setup_table_lists_the_generated_names(app, settings, tmp_path):
    from gui.building_page import BuildingPage
    page = BuildingPage(settings)
    page.set_project(project(tmp_path))
    m = page.meas_table
    assert [m.item(r, 0).text() for r in range(m.rowCount())] == [
        "airborne A to B", "airborne A to C (louder speaker)", "airborne A to B (broken)",
        "impact A to B (carpet)"]


def test_visibility_checkbox_updates_charts(app, settings, tmp_path):
    from PySide6 import QtCore
    from gui.building_page import BuildingPage
    page = BuildingPage(settings)
    page.set_project(project(tmp_path))
    page.air_table.item(0, 0).setCheckState(QtCore.Qt.Unchecked)                   # hide first one
    assert ("airborne", "airborne A to B") in page.hidden
    assert len(page.air_curves.legend.items) == 1
    assert page.air_curves.table.columnCount() == 2
    page.air_table.item(0, 0).setCheckState(QtCore.Qt.Checked)
    assert not page.hidden and len(page.air_curves.legend.items) == 2


def test_message_counts_errors(app, settings, tmp_path):
    from gui.building_page import BuildingPage
    page = BuildingPage(settings)
    got = []
    page.message.connect(got.append)
    page.set_project(project(tmp_path))
    assert got[-1] == "4 measurement(s), 1 with errors"


def test_rooms_are_kept_sorted(app, settings, tmp_path, monkeypatch):
    from gui import building_page as bp
    page = bp.BuildingPage(settings)
    p = project(tmp_path)
    p.rooms = [Room("B.1.02"), Room("0.2.02"), Room("B.G.02"), Room("0.1.03")]
    p.airborne, p.impact = [], []
    page.set_project(p)
    names = lambda: [page.rooms_table.item(i, 0).text()                          # noqa: E731
                     for i in range(page.rooms_table.rowCount())]
    assert names() == ["0.1.03", "0.2.02", "B.1.02", "B.G.02"]                    # sorted on opening

    class FakeRoomDialog:
        answer = None

        def __init__(self, settings, taken, room=None, parent=None):
            self.old = room

        def exec(self):
            return True

        def room(self):
            return FakeRoomDialog.answer or self.old

    monkeypatch.setattr(bp, "RoomDialog", FakeRoomDialog)
    FakeRoomDialog.answer = Room("0.1.04 New")
    page.add_room()
    assert names() == ["0.1.03", "0.1.04 New", "0.2.02", "B.1.02", "B.G.02"]      # inserted in place
    page.rooms_table.selectRow(0)
    FakeRoomDialog.answer = Room("Z last")
    page.edit_room()                                                              # rename -> moves
    assert names() == ["0.1.04 New", "0.2.02", "B.1.02", "B.G.02", "Z last"]


def test_edit_room_rename_keeps_measurements(app, settings, tmp_path, monkeypatch):
    from gui import building_page as bp
    page = bp.BuildingPage(settings)
    page.set_project(project(tmp_path))

    class FakeDialog:
        def __init__(self, settings, taken, room=None, parent=None):
            self.old = room

        def exec(self):
            return True

        def room(self):
            return Room("B renamed", self.old.rt_files, self.old.background_files)

    monkeypatch.setattr(bp, "RoomDialog", FakeDialog)
    page.rooms_table.selectRow(1)                                                   # room B
    page.edit_room()
    assert [r.name for r in page.project.rooms] == ["A", "B renamed", "C"]
    assert page.project.airborne[0].receiver_room == "B renamed"
    assert page.project.impact[0].receiver_room == "B renamed"
    assert page.air_table.item(0, 2).text() == "54"                                 # still evaluates
    assert page.air_table.item(0, 1).toolTip().startswith("airborne A to B renamed")   # name follows


def test_remove_room_in_use_is_refused_and_unused_removed(app, settings, tmp_path, monkeypatch):
    from PySide6 import QtWidgets
    from gui.building_page import BuildingPage
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda *a, **k: None)
    page = BuildingPage(settings)
    p = project(tmp_path)
    p.rooms.append(Room("Unused"))
    page.set_project(p)
    page.rooms_table.selectRow(1)                                                   # B is used
    page.remove_room()
    assert len(page.project.rooms) == 4
    page.rooms_table.selectRow(3)                                                   # 'Unused' sorts last
    page.remove_room()
    assert [r.name for r in page.project.rooms] == ["A", "B", "C"]


def test_duplicate_and_remove_measurement(app, settings, tmp_path, monkeypatch):
    from PySide6 import QtWidgets
    from gui.building_page import BuildingPage
    page = BuildingPage(settings)
    page.set_project(project(tmp_path))
    page.meas_table.selectRow(0)
    page.duplicate_measurement()
    assert [s.comment for s in page.project.airborne][:2] == ["", "copy"]
    page.meas_table.selectRow(1)
    page.duplicate_measurement()
    assert page.project.airborne[2].comment == "copy copy"
    monkeypatch.setattr(QtWidgets.QMessageBox, "question",
                        lambda *a, **k: QtWidgets.QMessageBox.Yes)
    page.meas_table.selectRow(1)
    page.remove_measurement()
    assert "airborne A to B (copy)" not in page.project.situation_names()
    # impact rows come after the airborne rows in the table
    page.meas_table.selectRow(page.meas_table.rowCount() - 1)
    page.duplicate_measurement()
    assert page.project.impact[1].comment == "carpet copy"
    page.meas_table.selectRow(page.meas_table.rowCount() - 2)
    page.duplicate_measurement()
    assert page.project.impact[1].comment == "carpet copy 2"


def test_rt_kind_and_background_change_recalculate(app, settings, tmp_path):
    from gui.building_page import BuildingPage
    page = BuildingPage(settings)
    page.set_project(project(tmp_path))
    page.rt_kind.setCurrentIndex(page.rt_kind.findData("edt"))                       # EDT missing at 100 Hz
    assert page.project.rt_kind == "edt" and page.dirty
    assert page.air_table.item(0, 2).text() == "-"
    assert "reverberation time missing" in page.air_table.item(0, 7).text()
    page.rt_kind.setCurrentIndex(page.rt_kind.findData("t30"))
    loud = make_variant(S / "C_L20.SVL", tmp_path / "loud.SVL", 40.0)
    page.bg_row.set_paths([str(loud)])                                               # emits changed
    assert page.project.background_files == [str(loud)]
    assert "within 6 dB" in page.air_table.item(0, 7).text()


def test_save_open_roundtrip_and_dirty_flag(app, settings, tmp_path):
    from gui.building_page import BuildingPage
    page = BuildingPage(settings)
    titles = []
    page.title_changed.connect(titles.append)
    page.set_project(project(tmp_path))
    page.mark_dirty()
    assert titles[-1] == "Demo *"
    assert page.save_to(tmp_path / "demo.json") and not page.dirty and titles[-1] == "Demo"
    other = BuildingPage(settings)
    assert other.open_path(tmp_path / "demo.json")
    assert other.air_table.item(0, 2).text() == "54" and other.imp_table.item(0, 2).text() == "44"
    assert other.imp_table.item(0, 1).text() == "A \u2192 B (carpet)"


def test_open_bad_project_does_not_crash(app, settings, tmp_path, monkeypatch):
    from PySide6 import QtWidgets
    from gui.building_page import BuildingPage
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a, **k: None)
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    page = BuildingPage(settings)
    assert page.open_path(bad) is False


def test_show_details_hands_files_to_single_page(app, settings, tmp_path, monkeypatch):
    import gui.app as ga
    from PySide6 import QtCore
    real = QtCore.QSettings
    monkeypatch.setattr(ga.QtCore, "QSettings", lambda *a, **k: real(str(tmp_path / "m.ini"),
                                                                     real.IniFormat))
    w = ga.MainWindow()
    w.building.set_project(project(tmp_path))
    w.building.meas_table.selectRow(0)
    w.building.show_details()
    assert w.tabs.currentWidget() is w.airborne
    assert w.airborne.result.rating.value == 54
    w.building.meas_table.selectRow(3)                                               # the impact one
    w.building.show_details()
    assert w.tabs.currentWidget() is w.impact and w.impact.result.rating.value == 44


def test_dialogs(app, settings, tmp_path):
    from gui.building_dialogs import RoomDialog, SituationDialog
    p = project(tmp_path)
    room = RoomDialog(settings, ["A"], p.rooms[1])
    assert room.room().name == "B" and room.room().rt_files == p.rooms[1].rt_files
    assert room.room().background_files == []
    room.own_bg.setChecked(True)
    room.bg.set_paths([str(S / "C_L20.SVL")])
    assert room.room().background_files == [str(S / "C_L20.SVL")]
    dlg = SituationDialog("airborne", p, settings, [], p.airborne[1])
    s = dlg.situation()
    assert (s.source_room, s.receiver_room, s.comment) == ("A", "C", "louder speaker")
    assert s.source_files == p.airborne[1].source_files
    assert "airborne A to C (louder speaker)" in dlg.preview.text()
    dlg2 = SituationDialog("impact", p, settings, [], p.impact[0])
    i = dlg2.situation()
    assert (i.receiver_room, i.tapping_room, i.comment, i.tapping_files) == \
        ("B", "A", "carpet", p.impact[0].tapping_files)
    assert "impact A to B (carpet)" in dlg2.preview.text()


def test_dialog_preview_follows_input_and_duplicates_are_refused(app, settings, tmp_path,
                                                                 monkeypatch):
    from PySide6 import QtWidgets
    from gui.building_dialogs import SituationDialog
    warnings = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda parent, title, text: warnings.append(text))
    p = project(tmp_path)
    taken = [x.base_name for x in (*p.airborne, *p.impact)]
    dlg = SituationDialog("impact", p, settings, taken)
    dlg.source.set_value("A")
    dlg.receiver.set_value("B")
    assert "impact A to B</b>" in dlg.preview.text()                                 # no comment yet
    dlg.comment.setText("tile")
    assert "impact A to B (tile)" in dlg.preview.text()
    dlg.comment.setText("carpet")                                                    # already exists
    dlg.accept()
    assert warnings and "Add a comment to tell them apart" in warnings[-1]
    assert dlg.result() == 0                                                         # still open
    dlg.comment.setText("tile")
    dlg.accept()
    assert dlg.result() == 1                                                         # accepted
    assert dlg.situation().comment == "tile"


def test_airborne_dialog_needs_two_different_rooms(app, settings, tmp_path, monkeypatch):
    from PySide6 import QtWidgets
    from gui.building_dialogs import SituationDialog
    warnings = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda parent, title, text: warnings.append(text))
    dlg = SituationDialog("airborne", project(tmp_path), settings, [])
    dlg.source.set_value("A")
    dlg.receiver.set_value("A")
    dlg.accept()
    assert "must be different rooms" in warnings[-1] and dlg.result() == 0


class FakeSituationDialog:
    """Stands in for the modal dialog: returns a prepared answer."""
    answer = None            # the situation to return, or None for Cancel
    new_room = None          # a room the user 'creates' inside the dialog

    def __init__(self, kind, project, settings, taken, situation=None, parent=None):
        self.project = project
        self.kind = kind

    def exec(self):
        if self.new_room is not None:
            self.project.rooms.append(self.new_room)
        return self.answer is not None

    def situation(self):
        return self.answer


def test_add_and_edit_measurement_dirty_only_when_changed(app, settings, tmp_path, monkeypatch):
    from gui import building_page as bp
    monkeypatch.setattr(bp, "SituationDialog", FakeSituationDialog)
    page = bp.BuildingPage(settings)
    page.set_project(project(tmp_path))
    assert not page.dirty
    FakeSituationDialog.answer, FakeSituationDialog.new_room = None, None
    page.add_measurement("airborne")                                             # Cancel
    assert not page.dirty and len(page.project.airborne) == 3
    page.meas_table.selectRow(0)
    page.edit_measurement()                                                      # Cancel
    assert not page.dirty
    FakeSituationDialog.new_room = Room("New")                                   # only a room made
    page.add_measurement("airborne")
    assert page.dirty and [r.name for r in page.project.rooms][-1] == "New"
    assert len(page.project.airborne) == 3
    page.dirty = False
    FakeSituationDialog.new_room = None
    f = lambda n: str(S / n)                                                     # noqa: E731
    FakeSituationDialog.answer = AirborneSituation("B", "C", [f("A_L2.SVL")], [f("B_L2.SVL")])
    page.add_measurement("airborne")
    assert page.dirty and page.project.airborne[-1].base_name == "airborne B to C"
    assert page.air_table.rowCount() == 4
    FakeSituationDialog.answer = ImpactSituation("C", [f("B_L4.SVL")], comment="tile")
    page.meas_table.selectRow(page.meas_table.rowCount() - 1)
    page.edit_measurement()                                                      # replaces the impact row
    assert page.project.impact[0].comment == "tile" and page.imp_table.item(0, 2).text() == "44"


# ------------------------------------------------------------------ requirements
def test_requirements_show_in_tables_summary_and_bars(app, settings, tmp_path):
    from gui.building_page import BuildingPage
    page = BuildingPage(settings)
    p = project(tmp_path)
    p.airborne[0].requirement = 54          # 54 -> complies, margin 0
    p.airborne[1].requirement = 90          # far above -> does not comply
    p.impact[0].requirement = 40            # 44 > 40 -> does not comply
    page.set_project(p)
    at, it = page.air_table, page.imp_table
    assert at.item(0, 5).text() == "\u2265 54 dB"
    assert at.item(0, 6).text() == "Complies (+0 dB)"
    value = int(at.item(1, 2).text())                                       # quieter receiver: > 54
    assert at.item(1, 6).text() == f"Does not comply (\u2212{90 - value} dB)"
    assert at.item(2, 5).text() == "" and at.item(2, 6).text() == ""          # no requirement
    assert it.item(0, 5).text() == "Does not comply (\u22124 dB)"
    assert it.item(0, 4).text() == "\u2264 40 dB"
    assert at.horizontalHeaderItem(5).text() == "Req. (DnT,w)"
    assert it.horizontalHeaderItem(4).text() == "Req. (L'nT,w)"
    assert at.item(0, 6).background().color().name() == "#d5f5e3"           # green
    assert at.item(1, 6).background().color().name() == "#f5b7b1"           # red
    assert at.item(2, 6).background().color().name() != "#d5f5e3"
    text = page.compliance.text()
    assert "1 comply" in text and "2 do not comply" in text and "without requirement" in text
    assert page.air_bars.plot.titleLabel.text == "DnT,w"


def test_basis_selection_changes_check_and_titles(app, settings, tmp_path):
    from gui.building_page import BuildingPage
    page = BuildingPage(settings)
    p = project(tmp_path)
    p.airborne[0].requirement = 54
    page.set_project(p)
    assert page.air_table.item(0, 6).text() == "Complies (+0 dB)"
    page.air_basis.setCurrentIndex(page.air_basis.findData("wc"))          # 54 + C(-1) = 53
    assert page.project.airborne_basis == "wc" and page.dirty
    assert page.air_table.horizontalHeaderItem(5).text() == "Req. (DnT,w + C)"
    assert page.air_table.item(0, 6).text() == "Does not comply (\u22121 dB)"
    assert page.air_bars.plot.titleLabel.text == "DnT,w + C"
    assert page.meas_table.item(0, 1).text() == "\u2265 54 dB"


def test_setup_table_shows_requirement(app, settings, tmp_path):
    from gui.building_page import BuildingPage
    page = BuildingPage(settings)
    p = project(tmp_path)
    p.airborne[1].requirement, p.impact[0].requirement = 50, 58
    page.set_project(p)
    m = page.meas_table
    assert [m.item(r, 1).text() for r in range(4)] == ["", "\u2265 50 dB", "", "\u2264 58 dB"]


def test_bulk_set_requirement(app, settings, tmp_path, monkeypatch):
    from PySide6 import QtWidgets
    from gui import building_page as bp
    page = bp.BuildingPage(settings)
    page.set_project(project(tmp_path))

    class FakeDialog:
        seen = None
        values_ = {}

        def __init__(self, project, n_airborne, n_impact, parent=None):
            FakeDialog.seen = (n_airborne, n_impact)

        def exec(self):
            return True

        def values(self):
            return FakeDialog.values_

    monkeypatch.setattr(bp, "RequirementsDialog", FakeDialog)
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda *a, **k: None)
    page.set_requirements()                                                 # nothing selected: only a hint
    assert not page.dirty
    page.meas_table.selectAll()
    FakeDialog.values_ = {"airborne": 54, "impact": 58}
    page.set_requirements()
    assert FakeDialog.seen == (3, 1) and page.dirty
    assert [s.requirement for s in page.project.airborne] == [54, 54, 54]
    assert page.project.impact[0].requirement == 58
    page.meas_table.clearSelection()
    page.meas_table.selectRow(3)                                            # only the impact row
    FakeDialog.values_ = {"impact": None}                                   # 0 = remove
    page.set_requirements()
    assert page.project.impact[0].requirement is None
    assert [s.requirement for s in page.project.airborne] == [54, 54, 54]   # untouched


def test_requirement_widgets_in_dialogs(app, settings, tmp_path):
    from gui.building_dialogs import RequirementsDialog, RequirementSpin, SituationDialog
    p = project(tmp_path)
    p.airborne[0].requirement = 52
    d = SituationDialog("airborne", p, settings, [], p.airborne[0])
    assert d.requirement.value() == 52 and d.situation().requirement == 52
    d.requirement.spin.setValue(0)
    assert d.situation().requirement is None                                # 0 = no requirement
    di = SituationDialog("impact", p, settings, [], p.impact[0])
    di.requirement.spin.setValue(58)
    assert di.situation().requirement == 58
    spin = RequirementSpin(p, "impact")
    assert spin.spin.specialValueText() == "no requirement" and spin.value() is None
    bulk = RequirementsDialog(p, 2, 0)
    assert list(bulk.rows) == ["airborne"]                                  # no impact rows selected
    bulk.rows["airborne"][1].spin.setValue(54)
    assert bulk.values() == {"airborne": 54}
    bulk.rows["airborne"][0].setChecked(False)
    assert bulk.values() == {}


def test_requirements_survive_save_and_open(app, settings, tmp_path):
    from gui.building_page import BuildingPage
    page = BuildingPage(settings)
    p = project(tmp_path)
    p.airborne[0].requirement, p.impact[0].requirement = 54, 58
    p.airborne_basis, p.impact_basis = "wctr", "wci"
    page.set_project(p)
    assert page.save_to(tmp_path / "req.json")
    other = BuildingPage(settings)
    assert other.open_path(tmp_path / "req.json")
    assert other.project.airborne[0].requirement == 54 and other.project.impact[0].requirement == 58
    assert other.air_basis.currentData() == "wctr" and other.imp_basis.currentData() == "wci"
    assert other.imp_table.horizontalHeaderItem(4).text() == "Req. (L'nT,w + C_I)"
    assert other.imp_table.item(0, 4).text() == "\u2264 58 dB"
