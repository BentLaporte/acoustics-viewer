"""Impact sound insulation page: L'nT and L'nT,w."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from calc.impact import ImpactResult, compute_impact
from calc.iso717 import REF_IMPACT
from calc.levels import LIMIT

from .widgets import (BasePage, RatingPlot, averages_note, band_axis, describe,
                      legend_next_to, minus, num, pen, signed, N_BANDS)

C_RAW, C_LI, C_BG, C_LNT = "#7fb3d5", "#1f618d", "#7f8c8d", "#117a65"


class ImpactPage(BasePage):
    ROLES = [("tapping", "Tapping machine (receiver)"),
             ("background", "Background (receiver)"), ("rt", "Reverberation time")]
    COLUMNS = ["Band [Hz]", "Li measured", "Lb", "Li - Lb", "Li corrected", "Correction",
               "T [s]", "L'nT", "Ref. curve", "Unfav. dev."]
    LEVELS_TAB = "Spectra and standardized level"
    RATING_TAB = "Rating L'nT,w"

    def build_levels_tab(self):
        self.plots = pg.GraphicsLayoutWidget()
        self.plots.ci.layout.setColumnFixedWidth(1, 250)
        self.p1 = self.plots.addPlot(row=0, col=0,
                                     title="Sound pressure levels in the receiving room")
        self.p1.setLabel("left", "Level", units="dB")
        band_axis(self.p1)
        self.c_raw = self.p1.plot(pen=pen(C_RAW, 1.5, QtCore.Qt.DashLine), symbol="t",
                                  symbolSize=6, symbolBrush=C_RAW)
        self.c_li = self.p1.plot(pen=pen(C_LI), symbol="o", symbolSize=6, symbolBrush=C_LI)
        self.c_bg = self.p1.plot(pen=pen(C_BG, 1.5, QtCore.Qt.DotLine), symbol="s",
                                 symbolSize=5, symbolBrush=C_BG)
        self.c_limit = self.p1.plot(pen=None, symbol="x", symbolSize=14,
                                    symbolPen=pen("#e67e22", 2))
        self.p2 = self.plots.addPlot(row=1, col=0, title="Standardized impact sound level")
        self.p2.setLabel("left", "L'nT", units="dB")
        self.p2.setLabel("bottom", "1/3-octave band centre frequency", units="Hz")
        band_axis(self.p2)
        self.p2.setXLink(self.p1)
        self.c_lnt = self.p2.plot(pen=pen(C_LNT), symbol="d", symbolSize=7,
                                  symbolBrush=C_LNT)
        legend_next_to(self.plots, 0, [(self.c_raw, "Li tapping machine (measured)"),
                                       (self.c_li, "Li (corrected)"),
                                       (self.c_bg, "Background Lb")])
        legend_next_to(self.plots, 1, [(self.c_lnt, "L'nT = Li - 10 lg(T/T0)")])
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
        return RatingPlot("Rating of L'nT (ISO 717-2)", "L'nT", "L'nT (measured)", "L'nT,w",
                          REF_IMPACT, deviation_above=True)

    # ---- hooks -------------------------------------------------------------------
    def compute(self, paths, rt_kind):
        return compute_impact(paths["tapping"], paths["background"], paths["rt"], rt_kind)

    def clear_levels(self):
        for c in (self.c_raw, self.c_li, self.c_bg, self.c_limit, self.c_lnt):
            c.setData([], [])

    def show_levels(self, r: ImpactResult):
        x = np.arange(N_BANDS)
        self.c_raw.setData(x, r.li_raw)
        self.c_li.setData(x, r.li)
        self.c_bg.setData(x, r.lb)
        lim = r.status == LIMIT
        self.c_limit.setData(x[lim], r.li_raw[lim])
        ok = np.isfinite(r.lnt)
        self.c_lnt.setData(x[ok], r.lnt[ok])
        self.p1.enableAutoRange(axis="y")
        self.p2.enableAutoRange(axis="y")

    def rating_values(self, r):
        return r.lnt

    def summary_html(self, r: ImpactResult) -> str:
        rt = r.rating
        if rt is None:
            missing = ", ".join(str(int(f)) for f in r.bands[~np.isfinite(r.lnt)])
            return (f"<b>Rating not possible:</b> no reverberation time ({r.t_kind.upper()}) "
                    f"for the bands {missing} Hz. Choose another value (T20/T30/EDT) or "
                    f"another reverberation time file.")
        text = (f"<b>L'<sub>nT,w</sub> (C<sub>I</sub>) = {rt.value} ({minus(r.ci)}) dB</b>"
                f" &nbsp;&nbsp; L'<sub>nT,w</sub> + C<sub>I</sub> = {rt.value + r.ci} dB "
                f"&nbsp;&nbsp; "
                f"reference curve shifted {signed(rt.shift)} dB, sum of unfavourable "
                f"deviations {rt.unfavourable_sum:.1f} dB (maximum 32.0 dB) &nbsp;&nbsp; "
                f"T = {r.t_kind.upper()}")
        if r.n_limit:
            text += (f"<br><span style='color:#b9770e'>Warning: {r.n_limit} band(s) are "
                     f"within 6 dB of the background, so L'nT is an upper limit there and "
                     f"the rating is only indicative.</span>")
        note = averages_note(r, ("tapping", "background", "rt"))
        if note:
            text += f"<br><span style='color:#555555'>{note}</span>"
        return text

    def table_row(self, r: ImpactResult, i: int):
        label = {"ok": "none", "corrected": "subtracted", "limit": "-1.3 dB, limit"}
        rt = r.rating
        return [str(int(r.bands[i])), num(r.li_raw[i]), num(r.lb[i]),
                num(r.li_raw[i] - r.lb[i]), num(r.li[i]), label[r.status[i]],
                num(r.t[i], 3), num(r.lnt[i]),
                "-" if rt is None else str(int(rt.curve[i])),
                "-" if rt is None or rt.deviations[i] == 0 else f"{rt.deviations[i]:.1f}"]

    def status_text(self, r: ImpactResult) -> str:
        msg = (f"Impact: {describe(r.names['tapping'])} / {describe(r.names['background'])} / "
               f"{describe(r.names['rt'])}  -  T = {r.t_kind.upper()}")
        if r.n_limit:
            msg += f"  -  {r.n_limit} band(s) within 6 dB of the background"
        if np.isnan(r.t).any():
            msg += "  -  reverberation time missing in some bands"
        return msg

    def hover_text(self, r: ImpactResult, i: int) -> str:
        return (f"{int(r.bands[i]):>5} Hz | Li {r.li[i]:5.1f} | Lb {r.lb[i]:5.1f} | "
                f"T {r.t[i]:5.2f} s | L'nT {r.lnt[i]:5.1f} dB")
