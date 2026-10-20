"""PDF report with installation noise: section, measurement page, notes, the method switch."""
import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import pytest

pypdf = pytest.importorskip("pypdf")
pytest.importorskip("reportlab")
pytest.importorskip("matplotlib")

from calc.building import (INTEGRATED_NOTE, InstallationSituation, Project, Room,  # noqa: E402
                           evaluate_project)
from calc.installation import Recording  # noqa: E402
from export import report_text as T  # noqa: E402
from export.pdf_report import ReportOptions, build_pdf_report, notes_shown  # noqa: E402

S = Path(__file__).parent.parent / "samples"
L22, BG = S / "installatiegeluid_L22.SVL", S / "installatiegeluid_BG_L39.SVL"
RT = [S / "installatiegeluid_RT_L15.SVL", S / "installatiegeluid_RT_L16.SVL"]
needs_samples = pytest.mark.skipif(not all(p.exists() for p in [L22, BG, *RT]),
                                   reason="installation noise sample files not present")
DATE = dt.date(2026, 10, 16)
INTEGRATED_NL = "ge\u00efntegreerde methode"


def project() -> Project:
    rooms = [Room("Slaapkamer 1", [str(p) for p in RT], [str(BG)]), Room("Technische ruimte")]
    return Project(name="Woning", rooms=rooms, installation=[
        InstallationSituation("Slaapkamer 1", [Recording(L22)], "Technische ruimte", "warmtepomp",
                              30),
        InstallationSituation("Slaapkamer 1", [Recording(L22, 2, 8)], "", "ventilatie", 45,
                              "lafmax")])


def build(p, tmp_path, **options):
    out = build_pdf_report(p, evaluate_project(p), tmp_path / "r.pdf",
                           ReportOptions(date=DATE, **options))
    reader = pypdf.PdfReader(str(out))
    return reader, [" ".join(page.extract_text().split()) for page in reader.pages]


@needs_samples
def test_installation_section_and_pages(tmp_path):
    reader, pages = build(project(), tmp_path, measurement_files=True)
    first = pages[0]
    assert first.startswith("Geluidsmetingen") and reader.metadata.title == "Woning - geluidsmetingen"
    assert "Installatiegeluid" in first and "Luchtgeluidisolatie" not in first
    assert "2 metingen (2 installatiegeluid)" in first
    assert T.RT_INSTALLATION in first and "T30 (RT30)" not in first   # no insulation measurements
    assert "Voldoet niet" in first and "Voldoet" in first
    assert INTEGRATED_NL in first and "NBN S 01-400-1" in first
    assert "Installatiegeluidresultaten moeten hoogstens" in first
    text = " ".join(pages)
    assert "Installatiegeluid Technische ruimte naar Slaapkamer 1 (warmtepomp)" in text
    assert "Installatiegeluid in Slaapkamer 1 (ventilatie)" in text
    assert "volledig (0-10)" in text and "2-8" in text          # time windows of the files
    assert "0,444 (T20)" in text and "0,446" in text             # T behind k, T20 marked
    assert "installatiegeluid_RT_L16.SVL" in text and str(S) not in text  # names, no folders
    assert len(pages) == 4                                       # first page, bars, 2 pages


@needs_samples
def test_integrated_method_switch(tmp_path):
    _, pages = build(project(), tmp_path, integrated_method_note=False)
    text = " ".join(pages)
    assert INTEGRATED_NL not in text.lower()
    assert "T20 gebruikt bij 400, 500, 630 Hz" in text               # the other remarks stay


@needs_samples
def test_requirements_off_and_no_measurement_pages(tmp_path):
    _, pages = build(project(), tmp_path, requirements=False, per_measurement_pages=False)
    text = " ".join(pages)
    assert "Voldoet" not in text and "Eis" not in text
    assert len(pages) == 2


@needs_samples
def test_inconclusive_note(tmp_path):
    from helpers import make_variant
    p = project()
    p.installation[0].recordings = [Recording(make_variant(L22, tmp_path / "q.SVL", -8.0))]
    p.installation[0].requirement = 33   # at least 33 dB without the background: could comply
    _, pages = build(p, tmp_path)
    assert "Niet conclusief (installatiegeluid)" in pages[0]
    assert "minder dan 6 dB boven het achtergrondgeluiddrukniveau (waarde overschat)" in pages[0]


def test_notes_shown_and_texts():
    # a stand-in with only what the two functions read (a real Evaluated needs result files)
    ev_notes = [INTEGRATED_NOTE, "background not checked"]
    ev = SimpleNamespace(kind="installation", name="installation in Slaapkamer 1 (warmtepomp)",
                         source_room="", receiver_room="Slaapkamer 1", comment="warmtepomp",
                         notes=ev_notes)
    assert notes_shown(ev, ReportOptions()) == ev_notes
    assert notes_shown(ev, ReportOptions(integrated_method_note=False)) == ["background not checked"]
    assert T.display_name(ev) == "installatiegeluid in Slaapkamer 1 (warmtepomp)"
    assert T.note_text(INTEGRATED_NOTE) == "ge\u00efntegreerde methode (bewegende microfoon)"
    assert T.note_text("T20 used at 400, 500 Hz (no T30)") == "T20 gebruikt bij 400, 500 Hz (geen T30)"
    assert T.note_text("room 'X' does not exist") == "ruimte 'X' bestaat niet"
    assert T.install_window(0, None, 10) == "volledig (0-10)"
    assert T.install_window(5, None, 30) == "5-30" and T.install_window(5, 20, 30) == "5-20"
