"""Shared building blocks of the viewer: file rows, the rating plot and the page base class."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

pg.setConfigOption("background", "w")
pg.setConfigOption("foreground", "#222222")
pg.setConfigOption("antialias", True)

BAND_LABELS = ["100", "125", "160", "200", "250", "315", "400", "500", "630", "800",
               "1k", "1.25k", "1.6k", "2k", "2.5k", "3.15k"]
N_BANDS = len(BAND_LABELS)
I500 = 7

C_REF, C_REF0, C_DEV, C_MEAS = "#c0392b", "#b2babb", "#e74c3c", "#117a65"


def pen(color, width=2, style=QtCore.Qt.SolidLine):
    return pg.mkPen(color=color, width=width, style=style)


def band_axis(plot: pg.PlotItem):
    plot.getAxis("bottom").setTicks([list(enumerate(BAND_LABELS))])
    plot.setXRange(-0.5, N_BANDS - 0.5, padding=0)
    plot.showGrid(x=True, y=True, alpha=0.25)


def minus(v) -> str:
    """Integer with a real minus sign, as used in the standards."""
    return f"{int(v):d}".replace("-", "\u2212")


def signed(v) -> str:
    return f"{int(v):+d}".replace("-", "\u2212")


def num(v, nd=1) -> str:
    return "-" if not np.isfinite(v) else f"{v:.{nd}f}"


def describe(names) -> str:
    """'A.SVL' for one file, '3 files' for several."""
    names = [names] if isinstance(names, str) else list(names)
    return names[0] if len(names) == 1 else f"{len(names)} files"


def averages_note(r, roles) -> str:
    """Explains which roles were averaged over several files (empty if none)."""
    labels = {"source": "source room", "receiver": "receiving room",
              "tapping": "tapping machine positions", "background": "background",
              "rt": "reverberation time decays"}
    parts = [f"{labels[k]}: {len(r.names[k])}" for k in roles if len(r.names[k]) > 1]
    if not parts:
        return ""
    text = ("Averaged over several files (levels: energy average, reverberation time: "
            "arithmetic mean) - " + "; ".join(parts))
    n = len(r.names["rt"])
    if r.t_counts is not None and n > 1 and (r.t_counts < n).any():
        text += "; the reverberation time is based on fewer decays in some bands"
    return text


def legend_next_to(layout_widget: pg.GraphicsLayoutWidget, row: int, items) -> pg.LegendItem:
    """Legend in its own column so it never covers the curves."""
    leg = pg.LegendItem(offset=(0, 0))
    for item, name in items:
        leg.addItem(item, name)
    layout_widget.addItem(leg, row=row, col=1)
    return leg


class FileRow(QtWidgets.QWidget):
    """One role (e.g. receiving room) with one or more files (positions / decays)."""
    changed = QtCore.Signal()

    def __init__(self, label: str, settings: QtCore.QSettings):
        super().__init__()
        self.settings = settings
        self._paths: list[str] = []
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = QtWidgets.QLabel(label)
        self.label.setFixedWidth(190)
        self.edit = QtWidgets.QLineEdit()
        self.edit.setReadOnly(True)
        self.edit.setPlaceholderText("no file selected")
        self.button = QtWidgets.QPushButton("Browse...")
        self.button.setToolTip("Choose one or more files (several positions are averaged)")
        self.button.clicked.connect(lambda: self.browse(add=False))
        self.add_button = QtWidgets.QPushButton("Add...")
        self.add_button.setToolTip("Add more files to the ones already chosen")
        self.add_button.clicked.connect(lambda: self.browse(add=True))
        self.clear_button = QtWidgets.QPushButton("Clear")
        self.clear_button.clicked.connect(lambda: self.set_paths([]))
        for w in (self.label,):
            lay.addWidget(w)
        lay.addWidget(self.edit, 1)
        for b in (self.button, self.add_button, self.clear_button):
            lay.addWidget(b)

    def paths(self) -> list[str]:
        return list(self._paths)

    def path(self) -> str:
        """First file (kept for convenience); '' if none."""
        return self._paths[0] if self._paths else ""

    def set_paths(self, paths, notify: bool = True):
        if isinstance(paths, (str, Path)):
            paths = [paths]
        self._paths = [str(p) for p in paths if str(p)]
        n = len(self._paths)
        if n == 0:
            self.edit.setText("")
        elif n == 1:
            self.edit.setText(self._paths[0])
        else:
            self.edit.setText(f"{n} files: " + ", ".join(Path(p).name for p in self._paths))
        self.edit.setToolTip("\n".join(self._paths))
        if notify:
            self.changed.emit()

    set_path = set_paths          # a single path works too

    def browse(self, add: bool = False):
        start = self.settings.value("last_dir", "")
        chosen, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, f"Select file(s): {self.label.text()}", start,
            "Svantek files (*.SVL *.svl)")
        if not chosen:
            return
        self.settings.setValue("last_dir", str(Path(chosen[0]).parent))
        if add:
            chosen = self._paths + [p for p in chosen if p not in self._paths]
        self.set_paths(chosen)


class RatingPlot:
    """Measured curve, shifted reference curve and unfavourable deviations (ISO 717)."""

    def __init__(self, title: str, ylabel: str, measured_name: str, w_name: str,
                 ref_unshifted, deviation_above: bool):
        self.w_name, self.above, self.measured_name = w_name, deviation_above, measured_name
        self.widget = pg.GraphicsLayoutWidget()
        self.widget.ci.layout.setColumnFixedWidth(1, 290)
        self.plot = self.widget.addPlot(row=0, col=0, title=title)
        self.plot.setLabel("left", ylabel, units="dB")
        self.plot.setLabel("bottom", "1/3-octave band centre frequency", units="Hz")
        band_axis(self.plot)
        x = np.arange(N_BANDS)
        self.c_ref0 = self.plot.plot(x, ref_unshifted, pen=pen(C_REF0, 1.5, QtCore.Qt.DotLine))
        self.bars = pg.BarGraphItem(x=[], height=[], width=0.35, y0=[],
                                    brush=pg.mkBrush(231, 76, 60, 150), pen=None)
        self.plot.addItem(self.bars)
        self.c_ref = self.plot.plot(pen=pen(C_REF, 2.5, QtCore.Qt.DashLine))
        self.c_meas = self.plot.plot(pen=pen(C_MEAS), symbol="d", symbolSize=8,
                                     symbolBrush=C_MEAS)
        self.c_w = self.plot.plot(pen=None, symbol="o", symbolSize=16, symbolBrush=None,
                                  symbolPen=pen("#000000", 2))
        self.w_label = pg.TextItem(anchor=(0, 1), color="#000000")
        self.plot.addItem(self.w_label)
        self.legend = pg.LegendItem(offset=(0, 0))
        self.widget.addItem(self.legend, row=0, col=1)
        # dummy items that only supply legend samples
        self.s_ref0 = pg.PlotDataItem(pen=pen(C_REF0, 1.5, QtCore.Qt.DotLine))
        self.s_ref = pg.PlotDataItem(pen=pen(C_REF, 2.5, QtCore.Qt.DashLine))
        self.s_dev = pg.PlotDataItem(pen=pen(C_DEV, 8))

    def clear(self):
        for c in (self.c_meas, self.c_ref, self.c_w):
            c.setData([], [])
        self.bars.setOpts(x=[], height=[], y0=[])
        self.w_label.setText("")
        self.legend.clear()

    def update(self, values, rating):
        """values: per-band curve (NaN allowed); rating: calc.iso717.Rating or None."""
        self.clear()
        values = np.asarray(values, float)
        x = np.arange(N_BANDS)
        ok = np.isfinite(values)
        self.c_meas.setData(x[ok], values[ok])
        self.legend.addItem(self.c_meas, self.measured_name)
        self.legend.addItem(self.s_ref0, "Reference curve (unshifted)")
        if rating is None:
            return
        self.c_ref.setData(x, rating.curve)
        self.legend.addItem(self.s_ref, f"Reference curve shifted {signed(rating.shift)} dB")
        self.legend.addItem(self.s_dev,
                            f"Unfavourable deviations (sum {rating.unfavourable_sum:.1f} dB)")
        dev = rating.deviations > 0
        v = np.round(values, 1)
        y0 = rating.curve[dev] if self.above else v[dev]     # bar spans curve <-> value
        self.bars.setOpts(x=x[dev], y0=y0, height=rating.deviations[dev])
        self.c_w.setData([I500], [rating.curve[I500]])
        self.w_label.setText(f"{self.w_name} = {rating.value} dB")
        self.w_label.setPos(I500 + 0.3, rating.curve[I500] + 1.5)


class BasePage(QtWidgets.QWidget):
    """A measurement page: file rows, reverberation time choice, tabs, table, hover line.

    Subclasses define ROLES, COLUMNS, the plots (build_levels_tab) and the content hooks.
    """
    ROLES: list[tuple[str, str]] = []
    COLUMNS: list[str] = []
    RATING_TAB = "Rating"
    HELP = "Select the measurement files."
    message = QtCore.Signal(str)

    # ---- hooks for subclasses --------------------------------------------------
    def build_levels_tab(self) -> QtWidgets.QWidget: raise NotImplementedError
    def make_rating_plot(self) -> RatingPlot: raise NotImplementedError
    def compute(self, paths: dict, rt_kind: str): raise NotImplementedError
    def show_levels(self, r): raise NotImplementedError
    def clear_levels(self): raise NotImplementedError
    def rating_values(self, r): raise NotImplementedError
    def summary_html(self, r) -> str: raise NotImplementedError
    def table_row(self, r, i) -> list: raise NotImplementedError
    def status_text(self, r) -> str: raise NotImplementedError
    def hover_text(self, r, i) -> str: raise NotImplementedError
    def hover_plots(self) -> list: raise NotImplementedError

    def __init__(self, settings: QtCore.QSettings):
        super().__init__()
        self.settings = settings
        self.result = None
        root = QtWidgets.QVBoxLayout(self)

        box = QtWidgets.QGroupBox("Measurement files")
        form = QtWidgets.QVBoxLayout(box)
        self.rows: dict[str, FileRow] = {}
        for key, label in self.ROLES:
            row = FileRow(label, settings)
            row.changed.connect(self.recalculate)
            self.rows[key] = row
            form.addWidget(row)
        opt = QtWidgets.QHBoxLayout()
        opt.addWidget(QtWidgets.QLabel("Reverberation time used:"))
        self.rt_kind = QtWidgets.QComboBox()
        for text, val in (("T30 (RT30)", "t30"), ("T20 (RT20)", "t20"), ("EDT", "edt")):
            self.rt_kind.addItem(text, val)
        self.rt_kind.currentIndexChanged.connect(self.recalculate)
        opt.addWidget(self.rt_kind)
        opt.addStretch(1)
        form.addLayout(opt)
        root.addWidget(box)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self.build_levels_tab(), self.LEVELS_TAB)
        self.summary = QtWidgets.QLabel()
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet("font-size: 15px; padding: 6px; background: #f4f6f7;"
                                   "border: 1px solid #d5d8dc;")
        self.rating_plot = self.make_rating_plot()
        rating_tab = QtWidgets.QWidget()
        rlay = QtWidgets.QVBoxLayout(rating_tab)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.addWidget(self.summary)
        rlay.addWidget(self.rating_plot.widget, 1)
        self.tabs.addTab(rating_tab, self.RATING_TAB)

        self.hover = QtWidgets.QLabel("Move the mouse over a plot to read the values per band.")
        self.hover.setStyleSheet("font-family: Consolas, monospace; padding: 2px;")
        top = QtWidgets.QWidget()
        tl = QtWidgets.QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(self.tabs, 1)
        tl.addWidget(self.hover)

        self.hover_targets = list(self.hover_plots()) + [self.rating_plot.plot]
        self.vlines = []
        for p in self.hover_targets:
            vl = pg.InfiniteLine(angle=90, movable=False, pen=pen("#999999", 1))
            vl.setVisible(False)
            p.addItem(vl, ignoreBounds=True)
            self.vlines.append(vl)
            p.scene().sigMouseMoved.connect(self.on_mouse)

        self.table = QtWidgets.QTableWidget(N_BANDS, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        split = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        split.addWidget(top)
        split.addWidget(self.table)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setChildrenCollapsible(False)
        root.addWidget(split, 1)
        self.clear()

    LEVELS_TAB = "Spectra"

    # ---- logic ---------------------------------------------------------------------
    def clear(self):
        self.clear_levels()
        self.rating_plot.clear()
        self.summary.setText("Select the measurement files to see the rating.")
        self.table.clearContents()

    def load(self, paths: dict):
        """Fill the file rows: a path or a list of paths per role (unknown roles ignored)."""
        for key, path in paths.items():
            if path and key in self.rows:
                self.rows[key].set_paths(path, notify=False)
        self.recalculate()

    def recalculate(self):
        paths = {k: r.paths() for k, r in self.rows.items()}
        if not all(paths.values()):
            names = dict(self.ROLES)
            self.message.emit("Still needed: " + ", ".join(
                names[k] for k, v in paths.items() if not v))
            return
        try:
            self.result = self.compute(paths, self.rt_kind.currentData())
        except Exception as exc:                 # file problems must not crash the GUI
            self.result = None
            self.clear()
            self.message.emit("Could not read the files.")
            QtWidgets.QMessageBox.warning(self, "Could not calculate", str(exc))
            return
        self.show_result(self.result)

    def show_result(self, r):
        self.show_levels(r)
        self.rating_plot.update(self.rating_values(r), r.rating)
        self.summary.setText(self.summary_html(r))
        for i in range(N_BANDS):
            for j, v in enumerate(self.table_row(r, i)):
                item = QtWidgets.QTableWidgetItem(v)
                item.setTextAlignment(QtCore.Qt.AlignCenter)
                if r.status[i] == "limit":
                    item.setBackground(QtGui.QColor("#fdebd0"))
                self.table.setItem(i, j, item)
        self.message.emit(self.status_text(r))

    def on_mouse(self, pos):
        if self.result is None:
            return
        for p in self.hover_targets:
            if p.sceneBoundingRect().contains(pos):
                self.show_hover(int(round(p.vb.mapSceneToView(pos).x())))
                return

    def show_hover(self, i: int):
        r = self.result
        if r is None or not 0 <= i < N_BANDS:
            for vl in self.vlines:
                vl.setVisible(False)
            return
        for vl in self.vlines:
            vl.setPos(i)
            vl.setVisible(True)
        text = self.hover_text(r, i)
        if r.rating is not None:
            text += f" | ref {r.rating.curve[i]:.0f} | dev {r.rating.deviations[i]:.1f}"
        self.hover.setText(text)
