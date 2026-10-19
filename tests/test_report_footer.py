"""Footer of the PDF report: a long project name wraps instead of running into the page number."""
import pytest

pypdf = pytest.importorskip("pypdf")
pytest.importorskip("reportlab")

from reportlab.pdfbase import pdfmetrics  # noqa: E402

from calc.building import Project  # noqa: E402
from export.pdf_report import (FONT, FOOTER_SIZE, ReportOptions, _register_fonts,  # noqa: E402
                               build_pdf_report, footer_lines)

LONG = ("Nieuwbouw van 48 appartementen met ondergrondse parkeergarage, handelsruimten en "
        "gemeenschappelijke tuin, fase 2, blok C, Kortrijksesteenweg 1234, 9000 Gent")


def test_footer_lines_wrap_and_fit():
    _register_fonts()
    width = 100 * 2.8346                                       # 100 mm in points
    assert footer_lines("Woning Peeters", width) == ["Woning Peeters"]
    lines = footer_lines(LONG, width)
    assert len(lines) == 2 and lines[1].endswith("…")     # too long even for two lines
    assert all(pdfmetrics.stringWidth(x, FONT, FOOTER_SIZE) <= width for x in lines)
    two = footer_lines(LONG[:110], width)                      # fits on two lines: no ellipsis
    assert len(two) == 2 and " ".join(two) == LONG[:110]


def test_report_with_a_long_name_keeps_the_whole_footer(tmp_path):
    out = build_pdf_report(Project(name=LONG), [], tmp_path / "r.pdf",
                           ReportOptions(per_measurement_pages=False))
    page = " ".join(pypdf.PdfReader(str(out)).pages[0].extract_text().split())
    assert "Pagina 1 van 1" in page and "Nieuwbouw van 48 appartementen" in page
