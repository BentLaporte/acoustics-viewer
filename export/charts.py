"""Charts for the report, drawn with matplotlib (no pyplot, no display needed).

Every function returns PNG bytes. All colours come from calc.colors so the report matches
the viewer.
"""
from __future__ import annotations

import io

import numpy as np
from matplotlib.figure import Figure

from calc.iso717 import BANDS, I500, REF_AIRBORNE, REF_IMPACT

BAND_LABELS = ["100", "125", "160", "200", "250", "315", "400", "500", "630", "800", "1k",
               "1.25k", "1.6k", "2k", "2.5k", "3.15k"]
DPI = 220
GREY, RED, GREEN = "#b2babb", "#c0392b", "#117a65"


def shorten(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n - 1] + "\u2026"


def _png(fig: Figure) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI)
    return buf.getvalue()


def _band_axis(ax, ylabel: str):
    ax.set_xticks(range(len(BANDS)), BAND_LABELS, fontsize=7)
    ax.set_xlim(-0.5, len(BANDS) - 0.5)
    ax.set_xlabel("1/3-octave band centre frequency [Hz]", fontsize=7.5)
    ax.set_ylabel(ylabel, fontsize=7.5)
    ax.tick_params(axis="y", labelsize=7)
    ax.grid(True, alpha=0.3, lw=0.5)


def bars_chart(items, axis_label: str, title: str, width_in: float = 6.85) -> bytes:
    """Horizontal bars, the name written above each bar, a black line = requirement.

    items: list of (label, colour, value or None, requirement or None)."""
    n = max(len(items), 1)
    fig = Figure(figsize=(width_in, 0.5 * n + 0.95), layout="constrained")
    ax = fig.add_subplot()
    top = max([v for _, _, v, _ in items if v] + [r for *_, r in items if r] + [10])
    for i, (label, color, value, req) in enumerate(items):
        ax.barh(i + 0.2, value or 0, height=0.42, color=color)
        ax.text(top * 0.004, i - 0.02, shorten(label, 70), va="bottom", ha="left", fontsize=7)
        ax.text(max(value or 0, req or 0) + top * 0.008, i + 0.2,
                "-" if value is None else str(value), va="center", fontsize=7.5,
                fontweight="bold")
        if req:
            ax.plot([req, req], [i - 0.03, i + 0.43], color="black", lw=2.2, solid_capstyle="butt")
    ax.set_xlim(0, top * 1.1)
    ax.set_ylim(n - 0.3, -0.5)
    ax.set_yticks([])
    ax.set_xlabel(f"{axis_label}; black line = requirement [dB]", fontsize=7.5)
    ax.tick_params(axis="x", labelsize=7)
    ax.grid(True, axis="x", alpha=0.3, lw=0.5)
    ax.set_title(title, fontsize=9, loc="left")
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    return _png(fig)


def curves_chart(items, ylabel: str, title: str, width_in: float = 6.85,
                 height_in: float = 3.1) -> bytes:
    """All curves of one kind on top of each other, the legend below the plot.

    items: list of (label, colour, dashed, curve per band, limit mask per band)."""
    fig = Figure(figsize=(width_in, height_in + 0.16 * len(items)), layout="constrained")
    ax = fig.add_subplot()
    x = np.arange(len(BANDS))
    for label, color, dashed, curve, limit in items:
        curve = np.asarray(curve, float)
        ok = np.isfinite(curve)
        ax.plot(x[ok], curve[ok], color=color, lw=1.6, ls="--" if dashed else "-", marker="o",
                ms=3, label=shorten(label, 48))
        lim = np.asarray(limit, bool) & ok
        if lim.any():
            ax.plot(x[lim], curve[lim], "x", color="#e67e22", ms=8, mew=1.8)
    _band_axis(ax, ylabel)
    ax.set_title(title, fontsize=9, loc="left")
    if items:
        fig.legend(*ax.get_legend_handles_labels(), loc="outside lower left", fontsize=6.8,
                   frameon=False, ncol=1)
    return _png(fig)


def rating_chart(ev, width_in: float = 6.85, height_in: float = 2.9) -> bytes:
    """Measured curve, shifted reference curve and unfavourable deviations of one measurement."""
    above = ev.kind == "impact"
    ref0 = REF_IMPACT if above else REF_AIRBORNE
    quantity = "L'nT" if above else "DnT"
    rt = ev.rating
    curve = np.asarray(ev.curve, float)
    x = np.arange(len(BANDS))
    fig = Figure(figsize=(width_in, height_in), layout="constrained")
    ax = fig.add_subplot()
    ax.plot(x, ref0, color=GREY, ls=":", lw=1.3, label="Reference curve (unshifted)")
    ok = np.isfinite(curve)
    if rt is not None:
        shift = f"{rt.shift:+d}".replace("-", "\u2212")
        dev = rt.deviations > 0
        bottom = rt.curve[dev] if above else np.round(curve, 1)[dev]
        ax.bar(x[dev], rt.deviations[dev], bottom=bottom, width=0.36, color="#e74c3c",
               alpha=0.65, label=f"Unfavourable deviations (sum {rt.unfavourable_sum:.1f} dB)")
        ax.plot(x, rt.curve, color=RED, ls="--", lw=1.8, label=f"Reference curve shifted {shift} dB")
    ax.plot(x[ok], curve[ok], color=GREEN, lw=1.6, marker="d", ms=4, label=f"{quantity} (measured)")
    if rt is not None:
        ax.plot([I500], [rt.curve[I500]], "o", mfc="none", mec="black", ms=11, mew=1.5)
        ax.set_title(f"{quantity},w = {rt.value} dB", fontsize=9, fontweight="bold", loc="right")
    lim = np.asarray(ev.result.status == "limit", bool) & ok
    if lim.any():
        ax.plot(x[lim], curve[lim], "x", color="#e67e22", ms=8, mew=1.8,
                label="Limit value (close to background)")
    _band_axis(ax, f"{quantity} [dB]")
    ax.legend(fontsize=6.5, frameon=False, loc="best")
    return _png(fig)
