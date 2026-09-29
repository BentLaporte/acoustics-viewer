"""Airborne sound insulation page: DnT, DnT,w (C; Ctr)."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from calc.airborne import AirborneResult, compute_airborne
from calc.iso717 import REF_AIRBORNE
from calc.levels import LIMIT

from .widgets import (BasePage, RatingPlot, averages_note, band_axis, describe,
                      legend_next_to, minus, num, pen, signed, N_BANDS)

C_SOURCE, C_RECV_RAW, C_RECV, C_BG = "#c0392b", "#7fb3d5", "#1f618d", "#7f8c8d"
C_D, C_DNT = "#7d3c98", "#117a65"


class AirbornePage(BasePage):
    ROLES = [("source", "Source room"), ("receiver", "Receiving room"),
             ("background", "Background (receiver)"), ("rt", "Reverberation time")]
    COLUMNS = ["Band [Hz]", "L1", "L2 measured", "Lb", "L2 - Lb", "L2 corrected",
               "Correction", "T [s]", "D", "DnT", "Ref. curve", "Unfav. dev."]
    LEVELS_TAB = "Spectra and level difference"
    RATING_TAB = "Rating DnT,w"

    def build_levels_tab(self):
        self.plots = pg.GraphicsLayoutWidget()
        self.plots.ci.layout.setColumnFixedWidth(1, 250)
        self.p1 = self.plots.addPlot(row=0, col=0, title="Sound pressure levels")
        self.p1.setLabel("left", "Level", units="dB")
        band_axis(self.p1)
        self.c_source = self.p1.plot(pen=pen(C_SOURCE), symbol="o", symbolSize=6,
                                     symbolBrush=C_SOURCE)
        self.c_recv_raw = self.p1.plot(pen=pen(C_RECV_RAW, 1.5, QtCore.Qt.DashLine),
                                       symbol="t", symbolSize=6, symbolBrush=C_RECV_RAW)
        self.c_recv = self.p1.plot(pen=pen(C_RECV), symbol="o", symbolSize=6,
                                   symbolBrush=C_RECV)
        self.c_bg = self.p1.plot(pen=pen(C_BG, 1.5, QtCore.Qt.DotLine), symbol="s",
                                 symbolSize=5, symbolBrush=C_BG)
        self.c_limit = self.p1.plot(pen=None, symbol="x", symbolSize=14,
                                    symbolPen=pen("#e67e22", 2))
        self.p2 = self.plots.addPlot(row=1, col=0, title="Level difference")
        self.p2.setLabel("left", "Level difference", units="dB")
        self.p2.setLabel("bottom", "1/3-octave band centre frequency", units="Hz")
        band_axis(self.p2)
        self.p2.setXLink(self.p1)
        self.c_d = self.p2.plot(pen=pen(C_D), symbol="o", symbolSize=6, symbolBrush=C_D)
        self.c_dnt = self.p2.plot(pen=pen(C_DNT), symbol="d", symbolSize=7,
                                  symbolBrush=C_DNT)
        legend_next_to(self.plots, 0, [(self.c_source, "Source room L1"),
                                       (self.c_recv_raw, "Receiving room L2 (measured)"),
                                       (self.c_recv, "Receiving room L2 (corrected)"),
                                       (self.c_bg, "Background Lb")])
        legend_next_to(self.plots, 1, [(self.c_d, "D = L1 - L2"),
                                       (self.c_dnt, "DnT (standardized)")])
        self.plots.ci.layout.setRowStretchFactor(0, 3)
        self.plots.ci.layout.setRowStretchFactor(1, 2)
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.plots, 1)
        return w

    def hover_plots(self):
        return [self.p1, self.p2]

    def make_rating_plot(self):
        return RatingPlot("Rating of DnT (ISO 717-1)", "DnT", "DnT (measured)", "DnT,w",
                          REF_AIRBORNE, deviation_above=False)

    # ---- hooks -------------------------------------------------------------------
    def compute(self, paths, rt_kind):
        return compute_airborne(paths["source"], paths["receiver"], paths["background"],
                                paths["rt"], rt_kind)

    def clear_levels(self):
        for c in (self.c_source, self.c_recv_raw, self.c_recv, self.c_bg, self.c_limit,
                  self.c_d, self.c_dnt):
            c.setData([], [])

    def show_levels(self, r: AirborneResult):
        x = np.arange(N_BANDS)
        self.c_source.setData(x, r.l1)
        self.c_recv_raw.setData(x, r.l2_raw)
        self.c_recv.setData(x, r.l2)
        self.c_bg.setData(x, r.lb)
        lim = r.status == LIMIT
        self.c_limit.setData(x[lim], r.l2_raw[lim])
        self.c_d.setData(x, r.d)
        ok = np.isfinite(r.dnt)
        self.c_dnt.setData(x[ok], r.dnt[ok])
        self.p1.enableAutoRange(axis="y")
        self.p2.enableAutoRange(axis="y")

    def rating_values(self, r):
        return r.dnt

    def summary_html(self, r: AirborneResult) -> str:
        rt = r.rating
        if rt is None:
            missing = ", ".join(str(int(f)) for f in r.bands[~np.isfinite(r.dnt)])
            return (f"<b>Rating not possible:</b> no reverberation time ({r.t_kind.upper()}) "
                    f"for the bands {missing} Hz. Choose another value (T20/T30/EDT) or "
                    f"another reverberation time file.")
        text = (f"<b>D<sub>nT,w</sub> (C; C<sub>tr</sub>) = {rt.value} "
                f"({minus(r.c)}; {minus(r.ctr)}) dB</b> &nbsp;&nbsp; "
                f"reference curve shifted {signed(rt.shift)} dB, sum of unfavourable "
                f"deviations {rt.unfavourable_sum:.1f} dB (maximum 32.0 dB) &nbsp;&nbsp; "
                f"T = {r.t_kind.upper()}")
        if r.n_limit:
            text += (f"<br><span style='color:#b9770e'>Warning: {r.n_limit} band(s) are "
                     f"within 6 dB of the background, so DnT is a lower limit there and "
                     f"the rating is only indicative.</span>")
        note = averages_note(r, ("source", "receiver", "background", "rt"))
        if note:
            text += f"<br><span style='color:#555555'>{note}</span>"
        return text

    def table_row(self, r: AirborneResult, i: int):
        label = {"ok": "none", "corrected": "subtracted", "limit": "-1.3 dB, limit"}
        rt = r.rating
        return [str(int(r.bands[i])), num(r.l1[i]), num(r.l2_raw[i]), num(r.lb[i]),
                num(r.l2_raw[i] - r.lb[i]), num(r.l2[i]), label[r.status[i]],
                num(r.t[i], 3), num(r.d[i]), num(r.dnt[i]),
                "-" if rt is None else str(int(rt.curve[i])),
                "-" if rt is None or rt.deviations[i] == 0 else f"{rt.deviations[i]:.1f}"]

    def status_text(self, r: AirborneResult) -> str:
        msg = (f"Airborne: {describe(r.names['source'])} / {describe(r.names['receiver'])} / "
               f"{describe(r.names['background'])} / {describe(r.names['rt'])}"
               f"  -  T = {r.t_kind.upper()}")
        if r.n_limit:
            msg += f"  -  {r.n_limit} band(s) within 6 dB of the background"
        if np.isnan(r.t).any():
            msg += "  -  reverberation time missing in some bands"
        return msg

    def hover_text(self, r: AirborneResult, i: int) -> str:
        return (f"{int(r.bands[i]):>5} Hz | L1 {r.l1[i]:5.1f} | L2 {r.l2[i]:5.1f} | "
                f"Lb {r.lb[i]:5.1f} | T {r.t[i]:5.2f} s | D {r.d[i]:5.1f} | "
                f"DnT {r.dnt[i]:5.1f} dB")
