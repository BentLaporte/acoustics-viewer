"""The level history of one file (LAeq and LAFmax per second) with a time window that is chosen
by dragging a shaded region or typing the start and end second. Used for installation noise
recordings (the operating cycle) and for background files (leaving out a disturbance)."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from calc.measurements import Recording
from svl.parser import SvlFile

from .widgets import pen

C_LEQ, C_MAX, C_REGION = "#1f618d", "#e67e22", (31, 97, 141, 45)


def window_text(rec: Recording, duration: int | None) -> str:
    end = rec.end if rec.end is not None else duration
    if rec.start == 0 and rec.end is None:
        return f"whole file (0-{duration} s)" if duration else "whole file"
    return f"{rec.start}-{end} s"


class LevelHistory(QtWidgets.QWidget):
    """LAeq and LAFmax per second of one file, with the time window as a shaded region."""
    window_changed = QtCore.Signal(int, object)          # start, end (None = to the end)

    def __init__(self, hint: str = "drag the shaded region over one operating cycle"):
        super().__init__()
        self.hint = hint
        self.n = 0
        self.plot = pg.PlotWidget()
        self.plot.setMinimumHeight(190)
        self.plot.setLabel("left", "Level", units="dB(A)")
        self.plot.setLabel("bottom", "Time", units="s")
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.setMouseEnabled(x=False, y=False)
        self.region = pg.LinearRegionItem(brush=pg.mkBrush(*C_REGION), movable=True)
        self.region.setZValue(-10)
        for line in self.region.lines:
            line.setPen(pen(C_LEQ, 2))
        self.region.sigRegionChanged.connect(self._region_moving)
        self.region.sigRegionChangeFinished.connect(self._region_done)
        self.start = QtWidgets.QSpinBox()
        self.end = QtWidgets.QSpinBox()
        for spin in (self.start, self.end):
            spin.setSuffix(" s")
            spin.setMinimumWidth(90)
            spin.valueChanged.connect(self._spins_changed)
        self.whole = QtWidgets.QPushButton("Whole file")
        self.whole.clicked.connect(self.use_whole_file)
        self.title = QtWidgets.QLabel()
        self.title.setStyleSheet("color: #444444;")
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.title, 1)
        row.addWidget(QtWidgets.QLabel("Window from"))
        row.addWidget(self.start)
        row.addWidget(QtWidgets.QLabel("to"))
        row.addWidget(self.end)
        row.addWidget(self.whole)
        # the legend sits under the chart so it never covers a curve
        legend = QtWidgets.QLabel(f"<b style='color:{C_LEQ}'>LAeq per second</b> &nbsp;&nbsp; "
                                  f"<b style='color:{C_MAX}'>LAFmax per second</b> &nbsp;&nbsp; "
                                  "<span style='color:#666666'>shaded = the time window used"
                                  "</span>")
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(row)
        lay.addWidget(self.plot, 1)
        lay.addWidget(legend)
        self.show_file(None)

    def show_file(self, f: SvlFile | None, rec: Recording | None = None, error: str = ""):
        """Draw the history of f with the window of rec; None = nothing selected."""
        self.plot.clear()
        self.n = 0 if f is None else f.duration_s
        enabled = self.n > 0
        for w in (self.start, self.end, self.whole):
            w.setEnabled(enabled)
        if not enabled:
            self.title.setText(error or "Select a file in the list to see its level history.")
            return
        self.title.setText(f"{rec.path.name}: {self.hint}")
        x = np.arange(self.n + 1)                          # second k spans k ... k + 1
        self.plot.plot(x, f.laeq_per_second(), stepMode="center", pen=pen(C_LEQ, 2))
        self.plot.plot(x, f.lafmax_per_second(), stepMode="center", pen=pen(C_MAX, 1))
        self.region.setBounds((0, self.n))
        self.plot.addItem(self.region)
        for spin in (self.start, self.end):
            spin.blockSignals(True)
            spin.setRange(0, self.n)
        start, end = rec.start, self.n if rec.end is None else rec.end
        self.start.setValue(start)
        self.end.setValue(end)
        for spin in (self.start, self.end):
            spin.blockSignals(False)
        self.region.blockSignals(True)
        self.region.setRegion((start, end))
        self.region.blockSignals(False)
        self.plot.setXRange(0, self.n, padding=0.02)

    def window(self) -> tuple[int, int | None]:
        start, end = self.start.value(), self.end.value()
        return start, (None if end >= self.n else end)

    def _region_moving(self):
        a, b = (int(round(v)) for v in self.region.getRegion())
        for spin, v in ((self.start, a), (self.end, b)):
            spin.blockSignals(True)
            spin.setValue(v)
            spin.blockSignals(False)

    def _region_done(self):
        a, b = (int(round(v)) for v in self.region.getRegion())
        a, b = max(0, min(a, self.n - 1)), min(self.n, max(b, a + 1))    # whole seconds, >= 1 s
        self._set(a, b)

    def _spins_changed(self):
        a, b = self.start.value(), self.end.value()
        if b <= a:                                        # keep at least one second
            b = min(self.n, a + 1)
            a = b - 1
        self._set(a, b)

    def use_whole_file(self):
        self._set(0, self.n)

    def _set(self, a: int, b: int):
        for spin, v in ((self.start, a), (self.end, b)):
            spin.blockSignals(True)
            spin.setValue(v)
            spin.blockSignals(False)
        self.region.blockSignals(True)
        self.region.setRegion((a, b))
        self.region.blockSignals(False)
        self.window_changed.emit(a, None if b >= self.n else b)
