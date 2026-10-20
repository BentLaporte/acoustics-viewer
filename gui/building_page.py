"""Building page: rooms and measurements of a whole building, compared side by side."""
from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from calc.building import (AIRBORNE_BASES, IMPACT_BASES, KINDS, Evaluated, Project, Room,
                           airborne_details_files, evaluate_project, impact_details_files,
                           load_project, save_project)
from export.report_options import ReportOptions

from .building_dialogs import ReportDialog, RequirementsDialog, RoomDialog, SituationDialog
from .installation_dialog import InstallationDialog
from calc.colors import style_of
from calc.iso717 import BANDS

from .thumbs import thumbnail
from .background_window import BackgroundRow
from .widgets import N_BANDS, band_axis, minus, num, pen

ROW_ERROR, ROW_WARN = "#f5b7b1", "#fdebd0"
CHECK_BG = {"complies": "#d5f5e3", "tolerance": "#eef6d5", "fails": "#f5b7b1",
            "inconclusive": "#fdebd0", "no_result": "#eaecee", "none": None}
CHECK_FG = {"complies": "#1e8449", "tolerance": "#6b8e23", "fails": "#c0392b",
            "inconclusive": "#b9770e"}


def _cell(text, align=QtCore.Qt.AlignCenter, bg=None):
    item = QtWidgets.QTableWidgetItem(text)
    item.setTextAlignment(align)
    item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
    if bg:
        item.setBackground(QtGui.QColor(bg))
    return item


def _table(headers, stretch_col=None):
    t = QtWidgets.QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    t.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
    h = t.horizontalHeader()
    h.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
    if stretch_col is not None:
        h.setSectionResizeMode(stretch_col, QtWidgets.QHeaderView.Stretch)
    return t


def shorten(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n - 1] + "\u2026"


class CurvesChart(QtWidgets.QWidget):
    """All curves of one kind on top of each other, plus the values per band in a table."""

    def __init__(self, title: str, ylabel: str):
        super().__init__()
        self.graph = pg.GraphicsLayoutWidget()
        self.graph.ci.layout.setColumnFixedWidth(1, 330)
        self.plot = self.graph.addPlot(row=0, col=0, title=title)
        self.plot.setLabel("left", ylabel, units="dB")
        self.plot.setLabel("bottom", "1/3-octave band centre frequency", units="Hz")
        band_axis(self.plot)
        self.legend = pg.LegendItem(offset=(0, 0))
        self.graph.addItem(self.legend, row=0, col=1)
        self.table = QtWidgets.QTableWidget(N_BANDS, 1)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        split = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        split.addWidget(self.graph)
        split.addWidget(self.table)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 1)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(split)
        self.update_items([])

    def update_items(self, items):
        """items: list of (label, colour, dashed, curve per band, limit mask per band)."""
        self.plot.clear()
        self.legend.clear()
        x = np.arange(N_BANDS)
        self.table.setColumnCount(1 + len(items))
        self.table.setHorizontalHeaderLabels(["Band [Hz]"] + [i[0] for i in items])
        self.table.horizontalHeader().setTextElideMode(QtCore.Qt.ElideRight)
        for r, hz in enumerate(BANDS):
            self.table.setItem(r, 0, _cell(str(int(hz))))
        for j, (label, color, dashed, curve, limit) in enumerate(items, start=1):
            curve = np.asarray(curve, float)
            limit = np.asarray(limit, bool)
            ok = np.isfinite(curve)
            style = QtCore.Qt.DashLine if dashed else QtCore.Qt.SolidLine
            c = self.plot.plot(x[ok], curve[ok], pen=pen(color, 2, style), symbol="o",
                               symbolSize=5, symbolBrush=color)
            self.legend.addItem(c, shorten(label, 50))
            if limit.any():                               # orange cross: only a limit value
                self.plot.plot(x[limit & ok], curve[limit & ok], pen=None, symbol="x",
                               symbolSize=13, symbolPen=pen("#e67e22", 2))
            head = self.table.horizontalHeaderItem(j)
            head.setToolTip(label)
            head.setForeground(QtGui.QBrush(QtGui.QColor(color)))
            for r in range(N_BANDS):
                self.table.setItem(r, j, _cell(num(curve[r]), bg=ROW_WARN if limit[r] else None))
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.plot.enableAutoRange()


class RatingBars:
    """Horizontal bars with the single-number rating of every measurement.

    The name of the measurement is written above its bar, so long automatic names need no axis.
    A black line on a bar marks its requirement.
    """

    def __init__(self, title: str, axis_label: str):
        self.widget = pg.GraphicsLayoutWidget()
        self.plot = self.widget.addPlot(title=title)
        self.plot.setLabel("bottom", f"{axis_label}; black line = requirement", units="dB")
        self.plot.showGrid(x=True, y=False, alpha=0.25)
        self.plot.invertY(True)
        self.plot.hideAxis("left")
        self.update_items([])

    def update_items(self, items, title: str | None = None):
        """items: list of (label, colour, value or None, requirement or None)."""
        if title:
            self.plot.setTitle(title)
        self.plot.clear()
        n = len(items)
        ys = np.arange(n)
        vals = [i[2] for i in items]
        widths = [0 if v is None else v for v in vals]
        if not n:
            return
        bars = pg.BarGraphItem(x0=0, y=ys + 0.16, height=0.42, width=widths,
                               brushes=[QtGui.QColor(i[1]) for i in items], pen=None)
        self.plot.addItem(bars)
        top = max(widths + [i[3] or 0 for i in items] + [10])
        for y, (label, _, v, req) in zip(ys, items):
            name = pg.TextItem(shorten(label, 44), anchor=(0, 1), color="#111111")
            name.setPos(top * 0.005, y + 0.0)            # just above its bar
            self.plot.addItem(name)
            end = pg.TextItem("-" if v is None else str(v), anchor=(0, 0.5), color="#222222")
            end.setPos(max(v or 0, req or 0), y + 0.16)
            self.plot.addItem(end)
            if req:
                self.plot.plot([req, req], [y - 0.1, y + 0.42], pen=pen("#000000", 3))
        self.plot.setXRange(0, top * 1.12, padding=0)
        self.plot.setYRange(-0.45, n - 0.25, padding=0)


class BuildingPage(QtWidgets.QWidget):
    message = QtCore.Signal(str)
    title_changed = QtCore.Signal(str)
    details_requested = QtCore.Signal(str, dict, str)      # kind, files by role, rt kind

    def __init__(self, settings: QtCore.QSettings):
        super().__init__()
        self.settings = settings
        self.project = Project()
        self.path: Path | None = None
        self.dirty = False
        self.evaluated: list[Evaluated] = []
        self.hidden: set[tuple[str, str]] = set()          # (kind, name) unticked in the tables

        outer = QtWidgets.QHBoxLayout(self)
        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        outer.addWidget(split)
        split.addWidget(self.build_setup())
        split.addWidget(self.build_results())
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        split.setSizes([470, 1030])
        self.populate_setup()
        self.refresh()

    # ------------------------------------------------------------------ setup panel
    def build_setup(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 4, 0)

        row = QtWidgets.QHBoxLayout()
        for text, slot in (("New", self.new_project), ("Open...", self.open_project),
                           ("Save", self.save), ("Save as...", self.save_as),
                           ("Export PDF...", self.export_pdf)):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.file_label = QtWidgets.QLabel()
        self.file_label.setStyleSheet("color: #666666;")
        self.file_label.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        lay.addWidget(self.file_label)

        box = QtWidgets.QGroupBox("Building")
        form = QtWidgets.QVBoxLayout(box)
        nr = QtWidgets.QHBoxLayout()
        nr.addWidget(QtWidgets.QLabel("Name:"))
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.editingFinished.connect(self.name_changed)
        nr.addWidget(self.name_edit, 1)
        form.addLayout(nr)
        self.bg_row = BackgroundRow("Building background", self.settings)
        self.bg_row.label.setFixedWidth(150)
        self.bg_row.changed.connect(self.background_changed)
        form.addWidget(self.bg_row)
        kr = QtWidgets.QHBoxLayout()
        kr.addWidget(QtWidgets.QLabel("Reverberation time used:"))
        self.rt_kind = QtWidgets.QComboBox()
        for text, val in (("T30 (RT30)", "t30"), ("T20 (RT20)", "t20"), ("EDT", "edt")):
            self.rt_kind.addItem(text, val)
        self.rt_kind.currentIndexChanged.connect(self.rt_kind_changed)
        kr.addWidget(self.rt_kind)
        kr.addStretch(1)
        form.addLayout(kr)
        br = QtWidgets.QHBoxLayout()
        br.addWidget(QtWidgets.QLabel("Requirements are checked against:"))
        self.air_basis = QtWidgets.QComboBox()
        for key, text in AIRBORNE_BASES.items():
            self.air_basis.addItem(text, key)
        self.imp_basis = QtWidgets.QComboBox()
        for key, text in IMPACT_BASES.items():
            self.imp_basis.addItem(text, key)
        self.air_basis.currentIndexChanged.connect(self.basis_changed)
        self.imp_basis.currentIndexChanged.connect(self.basis_changed)
        br.addWidget(self.air_basis)
        br.addWidget(self.imp_basis)
        # NBN S 01-400 in situ: a result may be 2 dB (installation 1 dB) worse than required
        self.nbn_tolerance = QtWidgets.QCheckBox("with NBN tolerance")
        self.nbn_tolerance.setToolTip(
            "NBN S 01-400-1:2022 5.4, 6.4, 8.4: a measured result complies when it is at most "
            "2 dB worse than the requirement (installation noise 1 dB); 4 dB (3 dB) for "
            "receiving rooms under 25 m3 that are not bedrooms. Such results are shown as "
            "'complies within tolerance'. Off: strict check.")
        self.nbn_tolerance.toggled.connect(self.tolerance_changed)
        br.addWidget(self.nbn_tolerance)
        br.addStretch(1)
        form.addLayout(br)
        lay.addWidget(box)

        rooms_box = QtWidgets.QGroupBox("Rooms (source and receiving rooms)")
        rl = QtWidgets.QVBoxLayout(rooms_box)
        self.rooms_table = _table(["Room", "Reverberation time", "Background", "Photos",
                                   "Volume"],
                                  stretch_col=1)
        self.rooms_table.doubleClicked.connect(self.edit_room)
        rl.addWidget(self.rooms_table)
        rl.addLayout(self.buttons([("Add room...", self.add_room), ("Edit...", self.edit_room),
                                   ("Remove", self.remove_room)]))
        lay.addWidget(rooms_box, 2)

        meas_box = QtWidgets.QGroupBox("Measurements")
        ml = QtWidgets.QVBoxLayout(meas_box)
        self.meas_table = _table(["Measurement (name is generated)", "Requirement"], stretch_col=0)
        self.meas_table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.meas_table.doubleClicked.connect(self.edit_measurement)
        ml.addWidget(self.meas_table)
        ml.addLayout(self.buttons([("Add airborne...", lambda: self.add_measurement("airborne")),
                                   ("Add impact...", lambda: self.add_measurement("impact")),
                                   ("Add installation...",
                                    lambda: self.add_measurement("installation"))]))
        ml.addLayout(self.buttons([("Edit...", self.edit_measurement),
                                   ("Duplicate", self.duplicate_measurement),
                                   ("Remove", self.remove_measurement),
                                   ("Show details", self.show_details)]))
        ml.addLayout(self.buttons([("Set requirement...", self.set_requirements)]))
        lay.addWidget(meas_box, 3)
        return w

    @staticmethod
    def buttons(spec):
        row = QtWidgets.QHBoxLayout()
        for text, slot in spec:
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(lambda _=False, s=slot: s())
            row.addWidget(b)
        row.addStretch(1)
        return row

    # ------------------------------------------------------------------ results panel
    def build_results(self) -> QtWidgets.QWidget:
        self.tabs = QtWidgets.QTabWidget()

        overview = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.air_table = _table(["Show", "Measurement", "DnT,w", "C", "Ctr", "Requirement",
                                 "Check", "Notes"], stretch_col=None)
        self.air_bars = RatingBars("DnT,w", "higher is better")
        self.imp_table = _table(["Show", "Measurement",
                                 "L'nT,w", "C_I", "Requirement", "Check", "Notes"],
                                stretch_col=None)
        self.imp_bars = RatingBars("L'nT,w", "lower is better")
        # installation noise: one A-weighted value per measurement, the quantity per row
        self.ins_table = _table(["Show", "Measurement", "Value", "Quantity", "Requirement",
                                 "Check", "Notes"], stretch_col=None)
        self.ins_bars = RatingBars("Installation noise", "lower is better")
        self.tables = {"airborne": self.air_table, "impact": self.imp_table,
                       "installation": self.ins_table}
        self.bars = {"airborne": self.air_bars, "impact": self.imp_bars,
                     "installation": self.ins_bars}
        self.sections = {}
        for kind, title in (("airborne", "Airborne sound insulation"), ("impact", "Impact sound"),
                            ("installation", "Installation noise")):
            table, bars = self.tables[kind], self.bars[kind]
            sec = QtWidgets.QWidget()
            self.sections[kind] = sec
            sl = QtWidgets.QVBoxLayout(sec)
            sl.setContentsMargins(0, 0, 0, 0)
            lab = QtWidgets.QLabel(f"<b>{title}</b>")
            sl.addWidget(lab)
            inner = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
            inner.addWidget(table)
            inner.addWidget(bars.widget)
            inner.setStretchFactor(0, 3)
            inner.setStretchFactor(1, 2)
            inner.setSizes([700, 330])
            sl.addWidget(inner, 1)
            overview.addWidget(sec)
            table.itemChanged.connect(self.visibility_changed)
        self.tabs.addTab(overview, "Overview")
        self.air_curves = CurvesChart("Standardized level difference DnT", "DnT")
        self.imp_curves = CurvesChart("Standardized impact sound level L'nT", "L'nT")
        self.tabs.addTab(self.air_curves, "Airborne: DnT per band")
        self.tabs.addTab(self.imp_curves, "Impact: L'nT per band")
        self.compliance = QtWidgets.QLabel()
        self.compliance.setTextFormat(QtCore.Qt.RichText)
        self.compliance.setWordWrap(True)
        self.compliance.setStyleSheet("font-size: 14px; padding: 5px; background: #f4f6f7;"
                                      "border: 1px solid #d5d8dc;")
        wrapper = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(wrapper)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.compliance)
        lay.addWidget(self.tabs, 1)
        return wrapper

    # ------------------------------------------------------------------ model <-> ui
    def set_project(self, project: Project, path: Path | None = None, dirty: bool = False):
        self.project, self.path, self.dirty = project, path, dirty
        self.project.sort_rooms()
        self.hidden.clear()
        self.populate_setup()
        self.refresh()
        self.update_title()

    def mark_dirty(self):
        self.dirty = True
        self.update_title()

    def update_title(self):
        name = self.project.name or "Building"
        self.file_label.setText(str(self.path) if self.path else "not saved yet")
        self.file_label.setToolTip(str(self.path) if self.path else "")
        self.title_changed.emit(f"{name}{' *' if self.dirty else ''}")

    def populate_setup(self):
        p = self.project
        self.name_edit.setText(p.name)
        self.bg_row.set_paths(p.background_files, notify=False)
        self.rt_kind.blockSignals(True)
        self.rt_kind.setCurrentIndex(max(0, self.rt_kind.findData(p.rt_kind)))
        self.rt_kind.blockSignals(False)
        for combo, value in ((self.air_basis, p.airborne_basis), (self.imp_basis, p.impact_basis)):
            combo.blockSignals(True)
            combo.setCurrentIndex(max(0, combo.findData(value)))
            combo.blockSignals(False)
        self.nbn_tolerance.blockSignals(True)
        self.nbn_tolerance.setChecked(p.nbn_tolerance)
        self.nbn_tolerance.blockSignals(False)

        t = self.rooms_table
        t.setRowCount(len(p.rooms))
        for i, r in enumerate(p.rooms):
            t.setItem(i, 0, _cell(r.name, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter))
            rt = _cell((self.files_text(r.rt_files) or "-")
                       + (" (other room)" if r.rt_from else ""))
            if r.rt_from:
                rt.setToolTip(f"Measured in: {r.rt_from}")
            t.setItem(i, 1, rt)
            t.setItem(i, 2, _cell("own: " + self.files_text(r.background_files)
                                  if r.background_files else "building"))
            photos = _cell(str(len(r.photos)) if r.photos else "-")
            if r.photos:                                   # first photo = main picture
                pix = thumbnail(r.photos[0].path, QtCore.QSize(40, 30))
                if pix is not None:
                    photos.setIcon(QtGui.QIcon(pix))
                photos.setToolTip("\n".join(Path(ph.path).name for ph in r.photos))
            t.setItem(i, 3, photos)
            vol = "-" if r.volume is None else f"{r.volume:g} m\u00b3"
            t.setItem(i, 4, _cell(vol + (", bedroom" if r.bedroom else "")))
        m = self.meas_table
        names = p.situation_names()
        reqs = [self.requirement_text(x.kind, x.requirement) for x in p.all_situations()]
        m.setRowCount(len(names))
        for i, (name, req) in enumerate(zip(names, reqs)):
            c = _cell(name, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
            c.setToolTip(name)
            m.setItem(i, 0, c)
            m.setItem(i, 1, _cell(req))

    @staticmethod
    def requirement_text(kind: str, value) -> str:
        """'>= 54 dB' for airborne (at least), '<= 58 dB' for impact (at most); '' if none."""
        if value is None:
            return ""
        return f"{'\u2265' if kind == 'airborne' else '\u2264'} {value} dB"

    @staticmethod
    def files_text(paths) -> str:
        if not paths:
            return ""
        return Path(paths[0]).name if len(paths) == 1 else f"{len(paths)} files"

    def name_changed(self):
        name = self.name_edit.text().strip() or "Building"
        if name != self.project.name:
            self.project.name = name
            self.mark_dirty()

    def background_changed(self):
        self.project.background_files = self.bg_row.paths()
        self.mark_dirty()
        self.refresh()

    def basis_changed(self):
        self.project.airborne_basis = self.air_basis.currentData()
        self.project.impact_basis = self.imp_basis.currentData()
        self.mark_dirty()
        self.populate_setup()                     # the requirement column names the basis
        self.refresh()

    def tolerance_changed(self, on: bool):
        self.project.nbn_tolerance = on
        self.mark_dirty()
        self.refresh()                            # the checks change

    def rt_kind_changed(self):
        self.project.rt_kind = self.rt_kind.currentData()
        self.mark_dirty()
        self.refresh()

    # ------------------------------------------------------------------ evaluation and display
    def refresh(self):
        self.evaluated = evaluate_project(self.project)
        self.hidden &= {(e.kind, e.name) for e in self.evaluated}      # drop renamed / removed
        self.update_overview()
        self.update_charts()
        n = len(self.evaluated)
        errors = sum(1 for e in self.evaluated if not e.ok)
        warn = sum(1 for e in self.evaluated if e.ok and e.notes)
        text = f"{n} measurement(s)" if n else "No measurements yet: add rooms, then measurements."
        if errors:
            text += f", {errors} with errors"
        if warn:
            text += f", {warn} with remarks"
        counts = self.check_counts()
        if counts["with"]:
            text += (f"; requirements: {counts['complies'] + counts['tolerance']} comply, "
                     f"{counts['fails']} do not "
                     f"comply, {counts['inconclusive']} not conclusive")
        self.update_compliance(counts)
        self.message.emit(text)

    def check_counts(self) -> dict:
        c = {"complies": 0, "tolerance": 0, "fails": 0, "inconclusive": 0, "no_result": 0,
             "none": 0}
        for e in self.evaluated:
            c[e.check.status] += 1
        c["with"] = len(self.evaluated) - c["none"]
        return c

    def update_compliance(self, c: dict):
        if not self.evaluated:
            self.compliance.setText("Add rooms and measurements to compare them.")
            return
        if not c["with"]:
            self.compliance.setText("No requirements set yet: give a measurement a requirement "
                                    "(Edit... or Set requirement...) to check compliance.")
            return
        parts = [f"<b style='color:{CHECK_FG['complies']}'>{c['complies']} comply</b>"]
        if c["tolerance"]:
            parts.append(f"<b style='color:{CHECK_FG['tolerance']}'>{c['tolerance']} comply "
                         "within the NBN tolerance</b>")
        parts.append(f"<b style='color:{CHECK_FG['fails']}'>{c['fails']} do not comply</b>")
        if c["inconclusive"]:
            parts.append(f"<b style='color:{CHECK_FG['inconclusive']}'>{c['inconclusive']} "
                         "not conclusive</b> (background noise could change the result)")
        if c["no_result"]:
            parts.append(f"{c['no_result']} without result")
        if c["none"]:
            parts.append(f"{c['none']} without requirement")
        self.compliance.setText("Requirements: " + ", ".join(parts))

    def color_index(self, e: Evaluated) -> int:
        return self.evaluated.index(e)

    def update_overview(self):
        p = self.project
        basis = {"airborne": AIRBORNE_BASES[p.airborne_basis], "impact": IMPACT_BASES[p.impact_basis]}
        # a section without measurements is hidden; an empty building shows the two insulation
        # sections, as before installation noise existed
        present = {e.kind for e in self.evaluated} or {"airborne", "impact"}
        for kind in KINDS:
            self.sections[kind].setVisible(kind in present)
        for kind, table in self.tables.items():
            table.blockSignals(True)
            # the requirement column is named after the quantity it is checked against
            # (installation noise: the quantity is per measurement, in its own column)
            req_col = 5 if kind == "airborne" else 4
            if kind in basis:
                table.horizontalHeaderItem(req_col).setText(f"Req. ({basis[kind]})")
                table.horizontalHeaderItem(req_col).setToolTip(
                    f"Requirement, checked against {basis[kind]}")
            head = table.horizontalHeader()
            head.setSectionResizeMode(1, QtWidgets.QHeaderView.Interactive)
            table.setColumnWidth(1, 250)
            items = [e for e in self.evaluated if e.kind == kind]
            table.setRowCount(len(items))
            left = QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
            center = QtCore.Qt.AlignCenter
            for i, e in enumerate(items):
                color, _ = style_of(self.color_index(e))
                show = QtWidgets.QTableWidgetItem()
                show.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
                show.setCheckState(QtCore.Qt.Unchecked if (kind, e.name) in self.hidden
                                   else QtCore.Qt.Checked)
                show.setBackground(QtGui.QColor(color))
                show.setData(QtCore.Qt.UserRole, e.name)
                show.setToolTip(e.name)
                table.setItem(i, 0, show)
                r = e.result
                value = str(e.value) if e.value is not None else "-"
                if kind == "airborne":
                    numbers = [value, minus(r.c) if r and r.c is not None else "-",
                               minus(r.ctr) if r and r.ctr is not None else "-"]
                elif kind == "impact":
                    numbers = [value, minus(r.ci) if r and r.ci is not None else "-"]
                else:
                    numbers = [value, e.basis_label]
                chk = e.check
                margin = "" if chk.margin is None else f" ({chk.margin:+d} dB)".replace("-", "\u2212")
                notes = "; ".join(e.notes)
                cells = ([(e.label, left)] + [(v, center) for v in numbers] +
                         [(self.requirement_text(kind, e.requirement), center),
                          (chk.text + margin, center), (notes, left)])
                bg = ROW_ERROR if not e.ok else (ROW_WARN if e.notes else None)
                tip = e.name + (f"\n{notes}" if notes else "")
                for j, (text, align) in enumerate(cells, start=1):
                    c = _cell(text, align, bg)
                    c.setToolTip(tip)
                    table.setItem(i, j, c)
                check_cell = table.item(i, req_col + 1)
                if CHECK_BG[chk.status]:
                    check_cell.setBackground(QtGui.QColor(CHECK_BG[chk.status]))
                if chk.status in CHECK_FG:
                    check_cell.setForeground(QtGui.QColor(CHECK_FG[chk.status]))
                    check_cell.setFont(self.bold())
                if e.value is not None:
                    table.item(i, 2).setFont(self.bold())
            table.blockSignals(False)

    @staticmethod
    def bold():
        f = QtGui.QFont()
        f.setBold(True)
        return f

    def visibility_changed(self, item):
        if item.column() != 0:
            return
        kind = next(k for k, t in self.tables.items() if t is item.tableWidget())
        key = (kind, item.data(QtCore.Qt.UserRole))
        if item.checkState() == QtCore.Qt.Checked:
            self.hidden.discard(key)
        else:
            self.hidden.add(key)
        self.update_charts()

    def visible(self, kind):
        return [e for e in self.evaluated if e.kind == kind and (kind, e.name) not in self.hidden]

    def update_charts(self):
        for kind, curves, bars in (("airborne", self.air_curves, self.air_bars),
                                   ("impact", self.imp_curves, self.imp_bars)):
            vis = self.visible(kind)
            curves.update_items([(e.label, *self.style(e), e.curve, e.result.status == "limit")
                                 for e in vis if e.ok])
            title = {"airborne": AIRBORNE_BASES[self.project.airborne_basis],
                     "impact": IMPACT_BASES[self.project.impact_basis]}[kind]
            bars.update_items([(e.label, self.style(e)[0], e.assessed, e.requirement)
                               for e in vis], title)
        vis = self.visible("installation")
        quantities = sorted({e.basis_label for e in vis})
        self.ins_bars.update_items([(f"{e.basis_label}: {e.label}", self.style(e)[0],
                                     e.assessed, e.requirement) for e in vis],
                                   " / ".join(quantities) or "Installation noise")

    def style(self, e):
        return style_of(self.color_index(e))

    # ------------------------------------------------------------------ rooms
    def selected_row(self, table):
        rows = table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def add_room(self):
        dlg = RoomDialog(self.settings, [r.name for r in self.project.rooms], parent=self)
        if dlg.exec():
            self.project.rooms.append(dlg.room())
            self.project.sort_rooms()
            self.changed()

    def edit_room(self, *_):
        i = self.selected_row(self.rooms_table)
        if i < 0:
            return
        old = self.project.rooms[i]
        dlg = RoomDialog(self.settings, [r.name for r in self.project.rooms if r is not old],
                         old, parent=self)
        if dlg.exec():
            new = dlg.room()
            if new.name != old.name:                      # keep the measurements attached
                for s in self.project.airborne:
                    s.source_room = new.name if s.source_room == old.name else s.source_room
                    s.receiver_room = new.name if s.receiver_room == old.name else s.receiver_room
                for s in self.project.impact:
                    s.receiver_room = new.name if s.receiver_room == old.name else s.receiver_room
                    s.tapping_room = new.name if s.tapping_room == old.name else s.tapping_room
                for s in self.project.installation:
                    s.receiver_room = new.name if s.receiver_room == old.name else s.receiver_room
                    s.source_room = new.name if s.source_room == old.name else s.source_room
            self.project.rooms[i] = new
            self.project.sort_rooms()
            self.changed()

    def users_of(self, room: str) -> list[str]:
        p = self.project
        other = {"airborne": "source_room", "impact": "tapping_room",
                 "installation": "source_room"}
        return [name for s, name in zip(p.all_situations(), p.situation_names())
                if room in (s.receiver_room, getattr(s, other[s.kind]))]

    def remove_room(self):
        i = self.selected_row(self.rooms_table)
        if i < 0:
            return
        room = self.project.rooms[i]
        users = self.users_of(room.name)
        if users:
            QtWidgets.QMessageBox.information(
                self, "Room in use",
                f"Room '{room.name}' is used by: {', '.join(users)}.\n"
                "Remove or change those measurements first.")
            return
        del self.project.rooms[i]
        self.changed()

    # ------------------------------------------------------------------ measurements
    def locate(self, row):
        """Table row -> (kind, index in the project list); rows follow all_situations()."""
        for kind in KINDS:
            n = len(self.project.situations(kind))
            if row < n:
                return kind, row
            row -= n
        raise IndexError("no such measurement")

    def situation_dialog(self, kind, taken, situation=None):
        if kind == "installation":
            return InstallationDialog(self.project, self.settings, taken, situation, parent=self)
        return SituationDialog(kind, self.project, self.settings, taken, situation, parent=self)

    def add_measurement(self, kind):
        n_rooms = len(self.project.rooms)
        taken = [x.base_name for x in self.project.all_situations()]
        dlg = self.situation_dialog(kind, taken)
        accepted = dlg.exec()
        if accepted:
            self.project.situations(kind).append(dlg.situation())
        if accepted or len(self.project.rooms) != n_rooms:     # rooms may be created in the dialog
            self.changed()

    def edit_measurement(self, *_):
        row = self.selected_row(self.meas_table)
        if row < 0:
            return
        kind, i = self.locate(row)
        lst = self.project.situations(kind)
        old = lst[i]
        n_rooms = len(self.project.rooms)
        taken = [x.base_name for x in self.project.all_situations() if x is not old]
        dlg = self.situation_dialog(kind, taken, old)
        accepted = dlg.exec()
        if accepted:
            lst[i] = dlg.situation()
        if accepted or len(self.project.rooms) != n_rooms:
            self.changed()

    def duplicate_measurement(self):
        row = self.selected_row(self.meas_table)
        if row < 0:
            return
        kind, i = self.locate(row)
        lst = self.project.situations(kind)
        clone = copy.deepcopy(lst[i])
        taken = {x.base_name for x in self.project.all_situations()}
        base, n = f"{clone.comment} copy".strip(), 2         # 'carpet copy', 'copy', 'copy 2'...
        clone.comment = base
        while clone.base_name in taken:
            clone.comment, n = f"{base} {n}", n + 1
        lst.insert(i + 1, clone)
        self.changed()

    def remove_measurement(self):
        row = self.selected_row(self.meas_table)
        if row < 0:
            return
        kind, i = self.locate(row)
        lst = self.project.situations(kind)
        name = self.project.situation_names()[row]
        ok = QtWidgets.QMessageBox.question(self, "Remove measurement",
                                            f"Remove '{name}' from the building?")
        if ok == QtWidgets.QMessageBox.Yes:
            del lst[i]
            self.changed()

    def selected_measurements(self):
        """[(kind, index in the project list)] of all selected rows of the measurements table."""
        rows = sorted(r.row() for r in self.meas_table.selectionModel().selectedRows())
        return [self.locate(r) for r in rows]

    def set_requirements(self):
        sel = self.selected_measurements()
        if not sel:
            QtWidgets.QMessageBox.information(
                self, "Set requirement",
                "Select one or more measurements first (Ctrl or Shift + click for several).")
            return
        n = {k: sum(1 for kind, _ in sel if kind == k) for k in KINDS}
        dlg = RequirementsDialog(self.project, n["airborne"], n["impact"], n["installation"],
                                 parent=self)
        if not dlg.exec():
            return
        values = dlg.values()
        for kind, i in sel:
            if kind in values:
                self.project.situations(kind)[i].requirement = values[kind]
        self.changed()

    def show_details(self):
        row = self.selected_row(self.meas_table)
        if row < 0:
            return
        kind, i = self.locate(row)
        if kind == "installation":             # its details (level history) are in its dialog
            self.edit_measurement()
            return
        if kind == "airborne":
            files = airborne_details_files(self.project, self.project.airborne[i])
        else:
            files = impact_details_files(self.project, self.project.impact[i])
        self.details_requested.emit(kind, files, self.project.rt_kind)

    def changed(self):
        self.mark_dirty()
        self.populate_setup()
        self.refresh()

    # ------------------------------------------------------------------ report
    def export_pdf(self):
        """Ask for the report details and a file, then write the PDF report."""
        if not self.evaluated:
            QtWidgets.QMessageBox.information(self, "Export PDF",
                                              "Add measurements to the building first.")
            return
        try:                                   # imported here: the viewer starts faster without
            from export.pdf_report import build_pdf_report, default_report_name
        except ImportError as exc:
            QtWidgets.QMessageBox.warning(
                self, "PDF export not available",
                f"{exc}\n\nInstall the required libraries with:\npip install -r requirements.txt")
            return
        left_out = sum(1 for e in self.evaluated if (e.kind, e.name) in self.hidden)
        dlg = ReportDialog(self.project, len(self.evaluated) - left_out, left_out, parent=self)
        if not dlg.exec():
            return
        info = dlg.info()
        if info != self.project.report:
            self.project.report = info
            self.mark_dirty()
        chosen = dlg.report_options().to_dict()               # remembered per project
        if chosen != ReportOptions.from_dict(self.project.report_options).to_dict():
            self.project.report_options = chosen
            self.mark_dirty()
        folder = self.path.parent if self.path else Path(self.settings.value("project_dir", ""))
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save PDF report", str(folder / default_report_name(self.project)),
            "PDF report (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        options = dlg.report_options()
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            build_pdf_report(self.project, self.evaluated, path, options, self.hidden)
        except Exception as exc:               # e.g. the file is open in a PDF viewer
            QtWidgets.QMessageBox.warning(self, "Could not create the report",
                                          f"{Path(path).name}: {exc}")
            return
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self.message.emit(f"Report saved: {path}")
        if dlg.open_after.isChecked():
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path))

    # ------------------------------------------------------------------ project files
    def maybe_save(self) -> bool:
        """True if it is fine to continue (saved, discarded, or nothing to save)."""
        if not self.dirty:
            return True
        answer = QtWidgets.QMessageBox.question(
            self, "Unsaved changes", "Save the changes to this building first?",
            QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard |
            QtWidgets.QMessageBox.Cancel)
        if answer == QtWidgets.QMessageBox.Cancel:
            return False
        if answer == QtWidgets.QMessageBox.Save:
            return self.save()
        return True

    def new_project(self):
        if self.maybe_save():
            self.set_project(Project())

    def open_project(self):
        if not self.maybe_save():
            return
        start = self.settings.value("project_dir", "")
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open building", start,
                                                        "Building project (*.json)")
        if path:
            self.open_path(path)

    def open_path(self, path):
        try:
            project = load_project(path)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Could not open", f"{Path(path).name}: {exc}")
            return False
        self.settings.setValue("project_dir", str(Path(path).parent))
        self.set_project(project, Path(path).resolve())
        return True

    def save(self) -> bool:
        return self.save_to(self.path) if self.path else self.save_as()

    def save_as(self) -> bool:
        start = str(self.path) if self.path else str(
            Path(self.settings.value("project_dir", "")) / f"{self.project.name}.json")
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save building", start,
                                                        "Building project (*.json)")
        if not path:
            return False
        if not path.lower().endswith(".json"):
            path += ".json"
        return self.save_to(Path(path))

    def save_to(self, path) -> bool:
        try:
            save_project(self.project, path)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Could not save", str(exc))
            return False
        self.settings.setValue("project_dir", str(Path(path).parent))
        self.path, self.dirty = Path(path).resolve(), False
        self.update_title()
        return True
