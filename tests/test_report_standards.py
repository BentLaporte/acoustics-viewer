"""What the standards ask of the report: method and test date on the first page, limit values
written as DnT >= ... / L'nT <= ... (ISO 16283-1/-2 clause 14) and band charts at 5 mm per
one-third octave and 20 mm per 10 dB (ISO 16283-1/-2 clause 12)."""
import datetime as dt
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

pypdf = pytest.importorskip("pypdf")
pytest.importorskip("reportlab")
pytest.importorskip("matplotlib")

from calc.building import (AirborneSituation, Project, Room,  # noqa: E402
                           evaluate_project)
from calc.examples import example_airborne  # noqa: E402
from export import charts  # noqa: E402
from export import report_text as T  # noqa: E402
from export.pdf_report import (ReportOptions, build_pdf_report, limit_text,  # noqa: E402
                               measurement_dates_text, method_lines)

S = Path(__file__).parent.parent / "samples"
NEED = ["luchtgeluid_bron_L2.SVL", "luchtgeluid_ontvangst_L2.SVL", "ontvangstruimte_BG_L20.SVL",
        "ontvangstruimte_RT_L11.SVL"]
needs_samples = pytest.mark.skipif(not all((S / n).exists() for n in NEED),
                                   reason="sample files missing")
GE, LE, MINUS = T.LIMIT_PREFIX["airborne"], T.LIMIT_PREFIX["impact"], chr(0x2212)


def png_size_mm(png: bytes) -> tuple[float, float]:
    """Width and height of a PNG at the chart resolution (the PDF shows it at that size)."""
    w, h = int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
    return w / charts.DPI * 25.4, h / charts.DPI * 25.4


# ----------------------------------------------------------------------------- numbers
def test_number_never_shows_minus_zero():
    assert T.number(-0.04) == "0,0"                     # rounds to zero: no sign
    assert T.number(-1.3) == MINUS + "1,3"
    assert T.number(None) == "-"


def test_limit_values_carry_the_sign_of_the_quantity():
    assert limit_text(45.3, True, "airborne") == GE + "45,3"      # DnT >= 45,3
    assert limit_text(45.3, True, "impact") == LE + "45,3"        # L'nT <= 45,3
    assert limit_text(45.3, False, "airborne") == "45,3"
    assert limit_text(np.nan, True, "airborne") == "-"            # no sign without a value


# ----------------------------------------------------------------------------- chart scale
def test_band_figure_has_the_scale_of_iso_16283():
    fig, ax = charts.band_figure(30, 70)
    pos = ax.get_position()
    w_mm, h_mm = fig.get_figwidth() * 25.4, fig.get_figheight() * 25.4
    assert pos.width * w_mm == pytest.approx(16 * 5.0)            # 5 mm per one-third octave
    assert pos.height * h_mm == pytest.approx(40 * 2.0)           # 20 mm per 10 dB


def test_rating_chart_is_shown_at_its_own_size_and_grows_only_when_needed():
    ev = example_airborne()
    w, h = png_size_mm(charts.rating_chart(ev))
    assert w == pytest.approx(charts.FIG_W_MM, abs=0.2)          # the text width of the page
    # a little room for photos fits under the legend: the figure does not change
    assert png_size_mm(charts.rating_chart(ev, reserve_mm=5))[1] == pytest.approx(h, abs=0.2)
    # a lot of room makes the figure taller (the plot keeps its size and place)
    assert png_size_mm(charts.rating_chart(ev, reserve_mm=200))[1] > 200


# ----------------------------------------------------------------------------- first page
def ev_with_days(*days, kind="airborne"):
    infos = [NS(measured_at=dt.datetime(2026, 9, d, 12, 0)) for d in days]
    return NS(kind=kind, ok=True, result=NS(info={"source": infos}, method="positions"))


def test_measurement_dates_are_listed_or_given_as_a_period():
    assert measurement_dates_text([ev_with_days(22, 28, 22)]) == \
        "22 september 2026, 28 september 2026"
    assert measurement_dates_text([ev_with_days(1, 2), ev_with_days(3, 4)]) == \
        "1 september 2026 tot en met 4 september 2026"
    assert measurement_dates_text([ev_with_days()]) == ""


def test_method_lines_name_only_the_kinds_in_the_report():
    on, off = ReportOptions(), ReportOptions(integrated_method_note=False)
    air, imp = ev_with_days(1), ev_with_days(1, kind="impact")
    assert method_lines([air], on) == [T.METHOD["airborne"]]
    assert method_lines([imp, air], on) == [T.METHOD["airborne"], T.METHOD["impact"]]
    inst = ev_with_days(1, kind="installation")
    assert method_lines([inst], on) == [T.METHOD["installation"]]
    inst.result.method = "integrated"                 # deviation from ISO 10052 6.3.4
    assert method_lines([inst], on) == [T.METHOD["installation"] +
                                        T.METHOD_INSTALLATION_DEVIATION]
    assert method_lines([inst], off) == [T.METHOD_INSTALLATION_FORMULAS]


@needs_samples
def test_report_names_method_and_date_and_marks_limit_values(tmp_path):
    from helpers import make_variant
    loud = make_variant(S / "ontvangstruimte_BG_L20.SVL", tmp_path / "loud.SVL", 22.0)
    p = Project(name="Limits", background_files=[str(S / "ontvangstruimte_BG_L20.SVL")])
    p.rooms = [Room("A"), Room("B", [str(S / "ontvangstruimte_RT_L11.SVL")], [str(loud)])]
    p.airborne = [AirborneSituation("A", "B", [str(S / "luchtgeluid_bron_L2.SVL")],
                                    [str(S / "luchtgeluid_ontvangst_L2.SVL")], "loud")]
    evs = evaluate_project(p)
    assert (evs[0].result.status == "limit").any()
    out = build_pdf_report(p, evs, tmp_path / "r.pdf",
                           ReportOptions(date=dt.date(2026, 10, 1), file_dates=False))
    pages = [" ".join(pg.extract_text().split()) for pg in pypdf.PdfReader(str(out)).pages]
    first = pages[0]
    assert T.FACT_TEST_DATE in first and "22 september 2026" in first   # also without file dates
    assert "ISO 16283-1:2014" in first and "ISO 717-1:2020" in first
    joined = " ".join(pages)
    assert f"grenswaarden (DnT {GE}" in joined                          # comparison caption
    assert any(f"{GE}4" in pg or f"{GE}5" in pg or f"{GE}6" in pg for pg in pages[2:])
