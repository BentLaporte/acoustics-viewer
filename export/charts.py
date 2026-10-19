"""Charts for the report, drawn with matplotlib (no pyplot, no display needed).

Every function returns PNG bytes. All colours come from calc.colors so the report matches
the viewer. The texts are Dutch (the report language) and numbers use a decimal comma.

The charts of values per band follow ISO 16283-1 / -2 clause 12: frequency on a logarithmic
scale with 5 mm per one-third octave band and 20 mm per 10 dB. Their plot area is placed at an
exact size (band_figure) and the PDF shows them at their own size (FIG_W_MM wide), so the scale
on paper is the scale of the standard.
"""
from __future__ import annotations

import io

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FixedLocator, FuncFormatter

from calc.iso717 import BANDS, I500, REF_AIRBORNE, REF_IMPACT
from calc.levels import round_tenth

from .report_text import comma, number

BAND_LABELS = ["100", "125", "160", "200", "250", "315", "400", "500", "630", "800", "1k",
               "1,25k", "1,6k", "2k", "2,5k", "3,15k"]
DPI = 220
GREY, RED, GREEN = "#b2babb", "#c0392b", "#117a65"
COMMA_AXIS = FuncFormatter(lambda v, _: comma(f"{v:g}").replace("-", "\u2212"))

# scale of the band charts (ISO 16283-1 / -2 clause 12) and the layout around the plot area
MM_PER_BAND, MM_PER_DB = 5.0, 2.0
FIG_W_MM = 174.0                    # the text width of the report page
LEFT_MM, BOTTOM_MM, TOP_MM, GAP_MM = 15.0, 11.0, 7.0, 5.0
PLOT_W_MM = MM_PER_BAND * len(BANDS)        # 80 mm for 100 ... 3150 Hz
SIDE_X_MM = LEFT_MM + PLOT_W_MM + GAP_MM    # the column right of the plot: legend (and photos)
SIDE_W_MM = FIG_W_MM - SIDE_X_MM
# octave centre frequencies are labelled, every one-third octave band gets a tick
OCTAVE_TICKS = {1: "125", 4: "250", 7: "500", 10: "1000", 13: "2000"}


def shorten(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n - 1] + "\u2026"


def _png(fig: Figure) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI)      # no tight bbox: the figure keeps its size
    return buf.getvalue()


def db_range(*arrays, step: int = 10, minimum: int = 30) -> tuple[int, int]:
    """Axis limits on whole multiples of 10 dB around the finite values (at least 30 dB)."""
    values = np.concatenate([np.asarray(a, float).ravel() for a in arrays])
    values = values[np.isfinite(values)]
    lo = int(np.floor(values.min() / step) * step) if values.size else 20
    hi = int(np.ceil(values.max() / step) * step) if values.size else 70
    if hi - lo < minimum:
        hi = lo + minimum
    return lo, hi


def band_figure(lo: int, hi: int, extra_height_mm: float = 0.0):
    """Figure FIG_W_MM wide with a plot area of exactly 5 mm per band and 2 mm per dB at the
    left; the space at the right is for the legend. Returns (figure, axes)."""
    plot_h = (hi - lo) * MM_PER_DB
    height = max(BOTTOM_MM + plot_h + TOP_MM, extra_height_mm)
    fig = Figure(figsize=(FIG_W_MM / 25.4, height / 25.4))
    ax = fig.add_axes([LEFT_MM / FIG_W_MM, (height - TOP_MM - plot_h) / height,
                       PLOT_W_MM / FIG_W_MM, plot_h / height])
    ax.set_ylim(lo, hi)
    ax.set_xlim(-0.5, len(BANDS) - 0.5)
    return fig, ax


def _band_axis(ax, ylabel: str):
    ax.xaxis.set_major_locator(FixedLocator(list(OCTAVE_TICKS)))
    ax.set_xticklabels(list(OCTAVE_TICKS.values()), fontsize=6.5)
    ax.xaxis.set_minor_locator(FixedLocator(range(len(BANDS))))
    ax.set_xlabel("Frequentie [Hz] (tertsbanden)", fontsize=7)
    ax.set_ylabel(ylabel, fontsize=7)
    ax.yaxis.set_major_locator(FixedLocator(np.arange(*ax.get_ylim(), 10).tolist()
                                            + [ax.get_ylim()[1]]))
    ax.yaxis.set_major_formatter(COMMA_AXIS)
    ax.tick_params(axis="both", labelsize=6.5)
    ax.grid(True, which="major", alpha=0.35, lw=0.5)
    ax.grid(True, which="minor", axis="x", alpha=0.12, lw=0.4)


def _legend_right(fig, ax, handles_labels, fontsize=6.3):
    top = ax.get_position().y1
    return fig.legend(*handles_labels, loc="upper left",
                      bbox_to_anchor=(SIDE_X_MM / FIG_W_MM, top),
                      fontsize=fontsize, frameon=False, borderaxespad=0)


def _legend_bottom_mm(fig, legend) -> float:
    """How far below the top of the figure the legend ends, in mm (measured, so long labels
    that wrap are taken into account)."""
    FigureCanvasAgg(fig)                        # a canvas that can measure text
    box = legend.get_window_extent(fig.canvas.get_renderer())
    return (fig.bbox.height - box.y0) / fig.dpi * 25.4


def bars_chart(items, axis_label: str, title: str, width_in: float = 6.85,
               show_requirement: bool = True) -> bytes:
    """Horizontal bars, the name written above each bar, a black line = requirement.

    items: list of (label, colour, value or None, requirement or None).
    show_requirement=False leaves the black lines and their legend text out."""
    n = max(len(items), 1)
    fig = Figure(figsize=(width_in, 0.5 * n + 0.95), layout="constrained")
    ax = fig.add_subplot()
    reqs = [r for *_, r in items if r] if show_requirement else []
    top = max([v for _, _, v, _ in items if v] + reqs + [10])
    for i, (label, color, value, req) in enumerate(items):
        ax.barh(i + 0.2, value or 0, height=0.42, color=color)
        ax.text(top * 0.004, i - 0.02, shorten(label, 70), va="bottom", ha="left", fontsize=7)
        end = max(value or 0, (req or 0) if show_requirement else 0)
        ax.text(end + top * 0.008, i + 0.2, "-" if value is None else str(value), va="center",
                fontsize=7.5, fontweight="bold")
        if show_requirement and req:
            ax.plot([req, req], [i - 0.03, i + 0.43], color="black", lw=2.2, solid_capstyle="butt")
    ax.set_xlim(0, top * 1.1)
    ax.set_ylim(n - 0.3, -0.5)
    ax.set_yticks([])
    ax.set_xlabel(f"{axis_label}; zwarte lijn = eis [dB]" if show_requirement
                  else f"{axis_label} [dB]", fontsize=7.5)
    ax.tick_params(axis="x", labelsize=7)
    ax.grid(True, axis="x", alpha=0.3, lw=0.5)
    ax.set_title(title, fontsize=9, loc="left")
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    return _png(fig)


def curves_chart(items, ylabel: str, title: str) -> bytes:
    """All curves of one kind on top of each other at the scale of ISO 16283 clause 12, the
    legend at the right of the plot.

    items: list of (label, colour, dashed, curve per band, limit mask per band)."""
    lo, hi = db_range(*[c for *_, c, _ in items]) if items else (20, 70)
    legend_mm = TOP_MM + 3.3 * len(items) + 4             # about 3,3 mm per legend line
    fig, ax = band_figure(lo, hi, extra_height_mm=legend_mm)
    x = np.arange(len(BANDS))
    for label, color, dashed, curve, limit in items:
        curve = np.asarray(curve, float)
        ok = np.isfinite(curve)
        ax.plot(x[ok], curve[ok], color=color, lw=1.4, ls="--" if dashed else "-", marker="o",
                ms=2.6, label=shorten(label, 46))
        lim = np.asarray(limit, bool) & ok
        if lim.any():
            ax.plot(x[lim], curve[lim], "x", color="#e67e22", ms=6, mew=1.5)
    _band_axis(ax, ylabel)
    ax.set_title(title, fontsize=8, loc="left")
    if items:
        _legend_right(fig, ax, ax.get_legend_handles_labels())
    return _png(fig)


def history_chart(laeq, lafmax, start: int, end: int, title: str, width_in: float = 6.85,
                  height_in: float = 1.9) -> bytes:
    """Level history of one installation noise file: LAeq and LAFmax per second (steps), the
    time window used shaded. end is exclusive (whole seconds)."""
    laeq, lafmax = np.asarray(laeq, float), np.asarray(lafmax, float)
    x = np.arange(len(laeq) + 1)                           # second k spans k ... k + 1
    fig = Figure(figsize=(width_in, height_in), layout="constrained")
    ax = fig.add_subplot()
    ax.axvspan(start, end, color="#1f618d", alpha=0.13, lw=0, label="Gebruikt tijdvenster")
    ax.stairs(laeq, x, baseline=None, color="#1f618d", lw=1.5, label="LAeq per seconde")
    ax.stairs(lafmax, x, baseline=None, color="#e67e22", lw=1.0, label="LAFmax per seconde")
    ax.set_xlim(0, len(laeq))
    ax.set_xlabel("Tijd [s]", fontsize=7.5)
    ax.set_ylabel("Niveau [dB(A)]", fontsize=7.5)
    ax.yaxis.set_major_formatter(COMMA_AXIS)
    ax.tick_params(labelsize=7)
    ax.grid(True, alpha=0.3, lw=0.5)
    ax.set_title(title, fontsize=8, loc="left")
    fig.legend(*ax.get_legend_handles_labels(), loc="outside right center", fontsize=6.5,
               frameon=False)
    return _png(fig)


def rating_chart(ev, reserve_mm: float = 0.0) -> bytes:
    """Measured curve, shifted reference curve and unfavourable deviations of one measurement,
    at the scale of ISO 16283 clause 12, the legend at the right of the plot.

    reserve_mm: free height to keep at the bottom of the column right of the plot (under the
    legend), where the report draws the room photos. The figure grows downward when needed;
    the plot itself keeps its place and its scale."""
    fig, legend = _rating_figure(ev)
    if reserve_mm > 0:
        needed = _legend_bottom_mm(fig, legend) + 2 + reserve_mm
        if needed > fig.get_figheight() * 25.4:
            fig, _ = _rating_figure(ev, extra_height_mm=needed)
    return _png(fig)


def _rating_figure(ev, extra_height_mm: float = 0.0):
    above = ev.kind == "impact"
    ref0 = REF_IMPACT if above else REF_AIRBORNE
    quantity = "L'nT" if above else "DnT"
    rt = ev.rating
    curve = np.asarray(ev.curve, float)
    x = np.arange(len(BANDS))
    lo, hi = db_range(curve, ref0, rt.curve if rt is not None else [])
    fig, ax = band_figure(lo, hi, extra_height_mm)
    ax.plot(x, ref0, color=GREY, ls=":", lw=1.2, label="Referentiecurve (onverschoven)")
    ok = np.isfinite(curve)
    if rt is not None:
        shift = f"{rt.shift:+d}".replace("-", "\u2212")
        dev = rt.deviations > 0
        bottom = rt.curve[dev] if above else round_tenth(curve)[dev]
        ax.bar(x[dev], rt.deviations[dev], bottom=bottom, width=0.4, color="#e74c3c",
               alpha=0.65,
               label=f"Ongunstige afwijkingen (som {number(rt.unfavourable_sum)} dB)")
        ax.plot(x, rt.curve, color=RED, ls="--", lw=1.6,
                label=f"Referentiecurve verschoven {shift} dB")
    ax.plot(x[ok], curve[ok], color=GREEN, lw=1.4, marker="d", ms=3.2,
            label=f"{quantity} (gemeten)")
    if rt is not None:
        ax.plot([I500], [rt.curve[I500]], "o", mfc="none", mec="black", ms=9, mew=1.3)
        ax.set_title(f"{quantity},w = {rt.value} dB", fontsize=8, fontweight="bold", loc="right")
    lim = np.asarray(ev.result.status == "limit", bool) & ok
    if lim.any():
        ax.plot(x[lim], curve[lim], "x", color="#e67e22", ms=6, mew=1.5,
                label="Grenswaarde (dicht bij het\nachtergrondgeluiddrukniveau)")
    _band_axis(ax, f"{quantity} [dB]")
    return fig, _legend_right(fig, ax, ax.get_legend_handles_labels())
