"""PDF report: content, options and robustness (the PDF is read back with pypdf)."""
import datetime as dt
from pathlib import Path

import pytest

pypdf = pytest.importorskip("pypdf")
pytest.importorskip("reportlab")
pytest.importorskip("matplotlib")

from calc.building import (AirborneSituation, ImpactSituation, Project, Room,  # noqa: E402
                           evaluate_project)
from export.pdf_report import ReportOptions, build_pdf_report, default_report_name  # noqa: E402

S = Path(__file__).parent.parent / "samples"
NEED = ["luchtgeluid_bron_L2.SVL", "luchtgeluid_ontvangst_L2.SVL", "contactgeluid_L4.SVL", "ontvangstruimte_BG_L20.SVL", "ontvangstruimte_RT_L11.SVL"]
needs_samples = pytest.mark.skipif(not all((S / n).exists() for n in NEED),
                                   reason="sample files missing")
DATE = dt.date(2026, 9, 30)


def f(n):
    return str(S / n)


def project() -> Project:
    p = Project(name="Test building", background_files=[f("ontvangstruimte_BG_L20.SVL")])
    p.rooms = [Room("A"), Room("B", [f("ontvangstruimte_RT_L11.SVL")])]
    p.airborne = [AirborneSituation("A", "B", [f("luchtgeluid_bron_L2.SVL")], [f("luchtgeluid_ontvangst_L2.SVL")], "wall", 54)]
    p.impact = [ImpactSituation("B", [f("contactgeluid_L4.SVL")], "A", "carpet", 40)]
    p.report.client, p.report.location = "Client Ltd", "Main Street 1"
    p.report.author, p.report.remarks = "J. Doe", "Furnished.\nDoors closed."
    return p


def read(path):
    r = pypdf.PdfReader(str(path))
    # line breaks inside table cells are layout, not content: compare with one space
    return r, [" ".join(page.extract_text().split()) for page in r.pages]


def build(p, tmp_path, options=None, hidden=(), name="r.pdf"):
    out = build_pdf_report(p, evaluate_project(p), tmp_path / name,
                           options or ReportOptions(date=DATE), hidden)
    return out, *read(out)


@needs_samples
def test_report_structure_and_content(tmp_path):
    out, reader, pages = build(project(), tmp_path)
    assert out.read_bytes()[:5] == b"%PDF-"
    # overview, comparison, airborne curves, impact curves, one page per measurement
    assert len(pages) == 6
    first = pages[0]
    for text in ("Geluidsmetingen", "Test building", "Client Ltd", "Main Street 1",
                 "J. Doe", "30 september 2026", "Furnished.", "Doors closed.",
                 "luchtgeluid", "Voldoet", "Voldoet niet", "2 metingen"):
        assert text in first, text
    assert "1 voldoet" in first and "1 voldoet niet" in first
    assert "A \u2192 B (wall)" in first and "A \u2192 B (carpet)" in first
    assert "Vergelijking" in pages[1]
    assert "per band" in pages[2] and "per band" in pages[3]
    assert "Luchtgeluid A naar B (wall)" in pages[4] and "Contactgeluid A naar B (carpet)" in pages[5]
    assert "luchtgeluid_bron_L2.SVL" in pages[4] and "contactgeluid_L4.SVL" in pages[5]                # file names only
    assert str(S) not in "".join(pages)                                      # no full paths
    assert "Pagina 6 van 6" in pages[5] and "Pagina 1 van 6" in first
    assert reader.metadata.title == "Test building - geluidsmetingen"
    assert reader.metadata.author == "J. Doe"


@needs_samples
def test_values_in_the_report_match_the_calculation(tmp_path):
    p = project()
    _, _, pages = build(p, tmp_path)
    a, i = evaluate_project(p)
    assert (a.value, i.value) == (54, 44)
    assert "54" in pages[4] and "\u22121" in pages[4]                        # DnT,w and C
    assert "+0 dB" in pages[0] and "\u22124 dB" in pages[0]                  # margins 54/54, 40/44
    assert "67,5" in pages[4]                                                # DnT at 3150 Hz


@needs_samples
def test_options_and_hidden(tmp_path):
    p = project()
    _, _, pages = build(p, tmp_path, ReportOptions(per_measurement_pages=False, date=DATE),
                        name="a.pdf")
    assert len(pages) == 4
    full, _, _ = build(p, tmp_path, name="b.pdf")
    _, _, no_bands = build(p, tmp_path, ReportOptions(per_band_tables=False, date=DATE),
                           name="c.pdf")
    caption = "DnT per tertsband [dB]"
    assert caption in " ".join(read(full)[1])
    assert caption not in " ".join(no_bands)
    # measurements unticked in the viewer are left out completely
    _, _, pages = build(p, tmp_path, hidden={("impact", "impact A to B (carpet)")}, name="d.pdf")
    joined = " ".join(pages)
    assert "carpet" not in joined and len(pages) == 4        # overview, comparison, curves, detail
    assert "1 meting" in pages[0]


@needs_samples
def test_problem_measurements_are_reported_not_fatal(tmp_path):
    p = project()
    p.airborne.append(AirborneSituation("A", "B", [f("luchtgeluid_bron_L2.SVL")], [str(S / "missing.SVL")],
                                        "missing file"))
    p.rt_kind = "t30"
    _, _, pages = build(p, tmp_path)
    assert "bestand niet gevonden: missing.SVL" in pages[0]
    assert len(pages) == 6                                   # the failed one has no own page
    p2 = project()
    p2.rt_kind = "edt"                                       # no rating possible
    _, _, pages2 = build(p2, tmp_path, name="edt.pdf")
    assert "nagalmtijd ontbreekt" in pages2[0] and "Beoordeling niet mogelijk" in " ".join(pages2)


@needs_samples
def test_special_characters_in_names_and_text(tmp_path):
    p = project()
    p.rooms += [Room("Caf\u00e9 <1> & Co")]
    p.airborne.append(AirborneSituation("Caf\u00e9 <1> & Co", "B", [f("luchtgeluid_bron_L2.SVL")],
                                        [f("luchtgeluid_ontvangst_L2.SVL")], "\u2265 & <b>bold</b>"))
    p.report.remarks = "Line with <tags> & ampersand \u2192 arrow"
    _, _, pages = build(p, tmp_path)
    joined = " ".join(pages)
    assert "Caf\u00e9 <1> & Co" in joined and "<b>bold</b>" in joined
    assert "Line with <tags> & ampersand \u2192 arrow" in pages[0]


@needs_samples
def test_many_measurements_paginate(tmp_path):
    p = project()
    for k in range(25):
        p.airborne.append(AirborneSituation("A", "B", [f("luchtgeluid_bron_L2.SVL")], [f("luchtgeluid_ontvangst_L2.SVL")],
                                            f"position {k}"))
        p.impact.append(ImpactSituation("B", [f("contactgeluid_L4.SVL")], "A", f"position {k}"))
    _, reader, pages = build(p, tmp_path, ReportOptions(per_measurement_pages=False, date=DATE))
    assert len(pages) > 6                                   # tables and charts flow over pages
    assert "position 24" in " ".join(pages)
    assert f"Pagina {len(pages)} van {len(pages)}" in pages[-1]


def test_empty_building(tmp_path):
    out = build_pdf_report(Project(name="Empty"), [], tmp_path / "e.pdf",
                           ReportOptions(date=DATE))
    _, pages = read(out)
    assert len(pages) == 1 and "Er zijn nog geen metingen" in pages[0]


def test_default_name_is_a_valid_file_name():
    assert default_report_name(Project(name='Site: A/B "x"?')) == "Site AB x - rapport.pdf"
    assert default_report_name(Project(name="  ")) == "Building - rapport.pdf"


# ------------------------------------------------------------------ room photos
def with_photos(tmp_path):
    from calc.building import Photo
    from helpers import make_photo
    p = project()
    p.rooms.append(Room("Unused room"))
    a1 = make_photo(tmp_path / "a1.jpg", (4000, 3000))
    a2 = make_photo(tmp_path / "a2.jpg", (800, 1000), (200, 100, 100))
    b1 = make_photo(tmp_path / "b1.jpg", (1200, 800), (100, 200, 100), orientation=6)
    u1 = make_photo(tmp_path / "u1.jpg", (600, 400))
    p.room("A").photos = [Photo(a1, "Source room, seen from the door"), Photo(a2)]
    p.room("B").photos = [Photo(b1, "Receiving room")]
    p.room("Unused room").photos = [Photo(u1, "Never mentioned")]
    return p


def images_per_page(reader):
    return [len(page.images) for page in reader.pages]


@needs_samples
def test_photos_page_and_measurement_strips(tmp_path):
    p = with_photos(tmp_path)
    out, reader, pages = build(p, tmp_path)
    # overview, ROOMS, comparison, airborne curves, impact curves, 2 measurement pages
    assert len(pages) == 7 and pages[1].startswith("Ruimten")
    text = pages[1]
    assert "Source room, seen from the door" in text and "Receiving room" in text
    assert "Never mentioned" not in " ".join(pages)                     # room not used by a measurement
    assert "Bronruimte bij 2 metingen" in text   # room A
    assert "Ontvangstruimte bij 2 metingen" in text                              # room B
    # pictures per page: overview 0, rooms 3 (2 of A + 1 of B), bar charts 2, curves 1 + 1,
    # measurement pages 3 (main photo of both rooms + the rating chart)
    assert images_per_page(reader) == [0, 3, 2, 1, 1, 3, 3]
    assert "Bronruimte: A" in pages[5] and "Ontvangstruimte: B" in pages[5]
    assert "Bronruimte: A" in pages[6]
    assert "Source room, seen from the door" in pages[5]                # caption of the main photo
    assert out.stat().st_size < 1_000_000                               # 4000x3000 photo shrunk


@needs_samples
def test_photos_can_be_left_out(tmp_path):
    p = with_photos(tmp_path)
    _, reader, pages = build(p, tmp_path, ReportOptions(room_photos=False, date=DATE))
    assert len(pages) == 6 and not any(p.startswith("Ruimten") for p in pages)
    assert images_per_page(reader) == [0, 2, 1, 1, 1, 1]                # only the charts remain
    assert "Source room, seen from the door" not in " ".join(pages)
    # rooms without photos: no photo page and no strips
    plain = project()
    _, reader2, pages2 = build(plain, tmp_path, name="plain.pdf")
    assert len(pages2) == 6 and "Ruimten" not in pages2[1][:10]
    assert "Bronruimte: A" not in " ".join(pages2)


@needs_samples
def test_hidden_measurements_take_their_photos_along(tmp_path):
    p = with_photos(tmp_path)
    hidden = {("airborne", "airborne A to B (wall)"), ("impact", "impact A to B (carpet)")}
    _, _, pages = build(p, tmp_path, hidden=hidden, name="h.pdf")
    assert "Source room, seen from the door" not in " ".join(pages)


@needs_samples
def test_unreadable_photo_does_not_stop_the_report(tmp_path):
    from calc.building import Photo
    p = with_photos(tmp_path)
    (tmp_path / "broken.jpg").write_bytes(b"not a picture")
    p.room("B").photos = [Photo(str(tmp_path / "broken.jpg"), "Broken one"),
                          Photo(str(tmp_path / "gone.jpg")), *p.room("B").photos]
    _, reader, pages = build(p, tmp_path, name="broken.pdf")
    assert "Foto kon niet worden gelezen: broken.jpg" in pages[1]
    assert "Foto kon niet worden gelezen: gone.jpg" in pages[1]
    assert "Receiving room" in pages[1]                                 # the good photo is still there
    assert len(pages) == 7


@needs_samples
def test_main_photo_missing_falls_back_to_name_only(tmp_path):
    from calc.building import Photo
    from helpers import make_photo
    p = project()
    p.room("A").photos = [Photo(str(tmp_path / "gone.jpg"), "x")]       # unreadable main photo
    p.room("B").photos = [Photo(make_photo(tmp_path / "b.jpg", (600, 400)), "B photo")]
    _, reader, pages = build(p, tmp_path)
    page = pages[5]
    assert "Ontvangstruimte: B" in page and "B photo" in page            # the strip is still made
    assert "Bronruimte: A" in page                                     # name without picture
    assert images_per_page(reader)[5] == 2                              # 1 photo (B) + the chart


@needs_samples
def test_many_photos_flow_over_pages(tmp_path):
    from calc.building import Photo
    from helpers import make_photo
    p = project()
    shots = [Photo(make_photo(tmp_path / f"s{i}.jpg", (900, 600), (20 * i, 100, 200 - 10 * i)),
                   f"Shot {i}") for i in range(9)]
    p.room("A").photos = shots
    p.room("B").photos = shots[:3]
    _, reader, pages = build(p, tmp_path, ReportOptions(per_measurement_pages=False, date=DATE))
    photo_pages = [i for i, t in enumerate(pages) if "Shot" in t]
    assert len(photo_pages) >= 2                                        # flowed over several pages
    assert all(f"Shot {i}" in " ".join(pages) for i in range(9))
    assert sum(images_per_page(reader)[i] for i in photo_pages) == 12   # 9 + 3, none lost


# ------------------------------------------------------------------ date and time per file
@needs_samples
def test_each_file_shows_its_measurement_date_and_time(tmp_path):
    _, _, pages = build(project(), tmp_path)
    airborne, impact = pages[4], pages[5]
    assert "Meetbestanden (datum en tijd van de meting)" in airborne
    # airborne: source luchtgeluid_bron_L2 12:11, receiver luchtgeluid_ontvangst_L2 12:16, background 28/09 11:40, RT 12:44
    assert "luchtgeluid_bron_L2.SVL (22/09/2026 12:11)" in airborne
    assert "luchtgeluid_ontvangst_L2.SVL (22/09/2026 12:16)" in airborne
    assert "ontvangstruimte_BG_L20.SVL (28/09/2026 11:40)" in airborne            # another day: visible in the report
    assert "ontvangstruimte_RT_L11.SVL (22/09/2026 12:44)" in airborne
    assert "contactgeluid_L4.SVL (22/09/2026 12:19)" in impact and "ontvangstruimte_BG_L20.SVL (28/09/2026 11:40)" in impact
    assert str(S) not in airborne                                  # still no folders


@needs_samples
def test_several_files_per_role_are_listed_each_with_its_time(tmp_path):
    p = project()
    p.airborne[0].receiver_files = [f("luchtgeluid_ontvangst_L2.SVL"), f("contactgeluid_L4.SVL")]
    _, _, pages = build(p, tmp_path)
    page = pages[4]
    assert "luchtgeluid_ontvangst_L2.SVL (22/09/2026 12:16)" in page and "contactgeluid_L4.SVL (22/09/2026 12:19)" in page


def test_when_text_formats_the_moment():
    from export.pdf_report import when_text
    assert when_text(dt.datetime(2026, 9, 2, 7, 5, 59)) == "02/09/2026 07:05"
    assert when_text(None) == ""


@needs_samples
def test_results_without_file_info_fall_back_to_names(tmp_path):
    p = project()
    ev = evaluate_project(p)
    for e in ev:
        e.result.info = None                                      # e.g. results made by older code
    out = build_pdf_report(p, ev, tmp_path / "old.pdf", ReportOptions(date=DATE))
    text = " ".join(" ".join(pg.extract_text().split()) for pg in pypdf.PdfReader(str(out)).pages)
    assert "luchtgeluid_bron_L2.SVL" in text and "(22/09/2026" not in text


# ------------------------------------------------------------------ equipment, optional dates
@needs_samples
def test_equipment_section_lists_the_instruments_and_what_they_measured(tmp_path):
    p = project()
    p.report.equipment = "Calibrator type 4231\nTapping machine Norsonic"
    _, _, pages = build(p, tmp_path)
    first = pages[0]
    assert "Apparatuur" in first and "Instrument Serienummer Gebruikt voor" in first
    # luchtgeluid_bron_L2 is from the instrument with serial 99942 (source room); luchtgeluid_ontvangst_L2/contactgeluid_L4/ontvangstruimte_BG_L20/ontvangstruimte_RT_L11 from 156226
    assert "SV 977D 99942 geluiddrukniveaus bronruimte" in first
    assert "SV 977D 156226 geluiddrukniveaus ontvangstruimte, contactgeluiddrukniveaus ontvangstruimte, achtergrondgeluiddrukniveau, nagalmtijd" in first
    assert "\u2022 Calibrator type 4231" in first and "\u2022 Tapping machine Norsonic" in first


@needs_samples
def test_equipment_only_counts_included_measurements(tmp_path):
    p = project()
    hidden = {("airborne", "airborne A to B (wall)")}                 # the only one using luchtgeluid_bron_L2
    _, _, pages = build(p, tmp_path, hidden=hidden)
    assert "99942" not in " ".join(pages)                              # that instrument is not listed
    assert "156226" in pages[0]


@needs_samples
def test_no_equipment_section_without_instruments_or_text(tmp_path):
    p = project()
    ev = evaluate_project(p)
    for e in ev:
        e.result.info = None
    out = build_pdf_report(p, ev, tmp_path / "n.pdf", ReportOptions(date=DATE))
    first = read(out)[1][0]
    assert "Apparatuur" not in first
    p.report.equipment = "Only free text"
    out = build_pdf_report(p, ev, tmp_path / "t.pdf", ReportOptions(date=DATE))
    first = read(out)[1][0]
    assert "Apparatuur" in first and "Only free text" in first and "Serienummer" not in first


@needs_samples
def test_file_dates_are_optional(tmp_path):
    p = project()
    _, _, with_dates = build(p, tmp_path, ReportOptions(date=DATE), name="a.pdf")
    _, _, no_dates = build(p, tmp_path, ReportOptions(file_dates=False, date=DATE), name="b.pdf")
    assert "luchtgeluid_bron_L2.SVL (22/09/2026 12:11)" in with_dates[4]
    assert "Meetbestanden (datum en tijd van de meting)" in with_dates[4]
    assert "22/09/2026" not in no_dates[4] and "28/09/2026" not in no_dates[4]
    assert "luchtgeluid_bron_L2.SVL" in no_dates[4] and "Meetbestanden" in no_dates[4]
    assert "datum en tijd" not in no_dates[4]
    assert "SV 977D" in no_dates[0]                                    # equipment stays


def test_equipment_text_survives_saving(tmp_path):
    from calc.building import Project, load_project, save_project
    p = Project(name="E")
    p.report.equipment = "Calibrator\nLoudspeaker"
    save_project(p, tmp_path / "e.json")
    assert load_project(tmp_path / "e.json").report.equipment == "Calibrator\nLoudspeaker"
    old = tmp_path / "old.json"
    old.write_text('{"schema": 2, "report": {"client": "X"}}')
    assert load_project(old).report.equipment == ""


# ------------------------------------------------------------------ switches (ReportOptions)
def test_every_switch_of_the_registry_is_an_option_and_the_other_way_round():
    from dataclasses import fields

    from export.report_options import GROUPS, TOGGLES
    assert {t.key for t in TOGGLES} == {f.name for f in fields(ReportOptions)} - {"date"}
    assert len({t.key for t in TOGGLES}) == len(TOGGLES)                   # no duplicates
    assert all(t.group in GROUPS and t.label for t in TOGGLES)
    assert all(getattr(ReportOptions(), t.key) is t.default for t in TOGGLES)


def test_options_round_trip_and_ignore_what_they_do_not_know():
    opts = ReportOptions(requirements=False, term_ctr=False, date=DATE)
    assert opts.to_dict()["requirements"] is False and "date" not in opts.to_dict()
    again = ReportOptions.from_dict(opts.to_dict(), date=DATE)
    assert again == opts
    messy = {"summary": False, "no_such_switch": False, "notes": "no", "equipment": 0,
             "term_c": None}
    got = ReportOptions.from_dict(messy)
    assert got.summary is False                                            # understood
    assert got.notes and got.equipment and got.term_c                      # not a bool: default
    assert ReportOptions.from_dict(None) == ReportOptions()


def test_switches_are_saved_in_the_project_file(tmp_path):
    from calc.building import load_project, save_project
    p = Project(name="S")
    save_project(p, tmp_path / "plain.json")
    assert "report_options" not in (tmp_path / "plain.json").read_text()   # nothing chosen: no key
    p.report_options = {"requirements": False, "notes": True}
    save_project(p, tmp_path / "s.json")
    assert load_project(tmp_path / "s.json").report_options == p.report_options
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema": 2, "report_options": {"summary": false, "x": 3, "y": "no"}}')
    assert load_project(bad).report_options == {"summary": False}          # only booleans survive
    bad.write_text('{"schema": 2, "report_options": [1, 2]}')
    assert load_project(bad).report_options == {}
    old = tmp_path / "old2.json"
    old.write_text('{"schema": 2, "report": {"client": "X"}}')
    assert load_project(old).report_options == {}                          # older project files


def test_dutch_text_helpers():
    import datetime as dt2

    from export import report_text as T
    assert T.date_text(dt2.date(2026, 10, 8)) == "8 oktober 2026"
    assert T.date_text(dt2.date(2026, 3, 1)) == "1 maart 2026"
    assert T.number(-3.5) == "\u22123,5" and T.number(0.812, 3) == "0,812"
    assert T.number(None) == "-" and T.number(float("nan")) == "-"
    assert T.count_metingen(1) == "1 meting" and T.count_metingen(3) == "3 metingen"


def test_notes_and_errors_of_the_calculation_are_translated_and_unknown_ones_kept():
    from export import report_text as T
    assert T.note_text("file not found: x.SVL") == "bestand niet gevonden: x.SVL"
    assert T.note_text("2 band(s) within 6 dB of background (lower limit)") == \
        "2 band(en) binnen 6 dB van het achtergrondgeluiddrukniveau (ondergrens)"
    assert T.note_text("1 band(s) within 6 dB of background (upper limit)").endswith("(bovengrens)")
    assert T.note_text("averaged over several files") == "gemiddeld over meerdere bestanden"
    assert T.note_text("receiving room 'Z' does not exist") == "ontvangstruimte 'Z' bestaat niet"
    assert T.note_text("no reverberation time files for room 'B'") == \
        "geen nagalmtijdbestanden voor ruimte 'B'"
    assert T.note_text("something we never thought of") == "something we never thought of"


def test_measurement_names_are_built_from_the_parts():
    from types import SimpleNamespace as NS

    from export import report_text as T
    ev = NS(kind="airborne", source_room="A to Z", receiver_room="B", comment=" muur ",
            name="airborne A to Z to B (muur) #2")
    assert T.display_name(ev) == "luchtgeluid A to Z naar B (muur) #2"     # ' to ' left alone
    ev = NS(kind="impact", source_room="", receiver_room="B", comment="", name="impact to B")
    assert T.display_name(ev) == "contactgeluid naar B"


def test_a_term_that_a_requirement_uses_stays_visible():
    from types import SimpleNamespace as NS

    from export.pdf_report import shown_terms
    p = Project(name="t", airborne_basis="wctr", impact_basis="wci")
    evs = [NS(kind="airborne", requirement=50), NS(kind="impact", requirement=None)]
    none = ReportOptions(term_c=False, term_ctr=False, term_ci=False)
    assert shown_terms(none, p, evs, "airborne") == {"ctr"}                # basis DnT,w + Ctr
    assert shown_terms(none, p, evs, "impact") == set()                    # no impact requirement
    assert shown_terms(ReportOptions(term_c=True, term_ctr=False, term_ci=False), p, evs,
                       "airborne") == {"c", "ctr"}
    assert shown_terms(ReportOptions(**{**none.__dict__, "requirements": False}), p, evs,
                       "airborne") == set()                                # no requirements shown


@needs_samples
def test_without_requirements_nothing_about_them_is_left(tmp_path):
    p = project()
    p.airborne[0].requirement = 54
    p.airborne_basis = "wc"
    _, _, on = build(p, tmp_path, name="on.pdf")
    _, reader, off = build(p, tmp_path, ReportOptions(requirements=False, date=DATE),
                           name="off.pdf")
    joined_on, joined_off = " ".join(on), " ".join(off)
    for word in ("Voldoet", "Toetsing", "Eisen:", "Eisen getoetst aan"):
        assert word in joined_on, word
    for word in ("Voldoet", "voldoet", "voldoen", "Eis", "Toetsing", "Eisen", "marge", "\u2265",
                 "\u2264", "Niet conclusief", "Eisen getoetst"):
        assert word not in joined_off, word
    assert "A \u2192 B (wall)" in off[0] and "54" in off[0]                # the results remain
    assert len(off) == len(on)                                             # same pages


@needs_samples
def test_overview_columns_follow_the_options():
    from export.pdf_report import _overview_table, styles
    p = project()
    evs = evaluate_project(p)
    st = styles()
    air, imp = [evs[0]], [evs[1]]

    def columns(options, kind="airborne"):
        table = _overview_table(air if kind == "airborne" else imp, kind, p, options, st)
        return len(table._colWidths)

    assert columns(ReportOptions()) == 7                       # name, DnT,w, C, Ctr, eis, toetsing, opm.
    assert columns(ReportOptions(), "impact") == 6             # name, L'nT,w, C_I, eis, toetsing, opm.
    assert columns(ReportOptions(term_c=False)) == 6
    assert columns(ReportOptions(term_c=False, term_ctr=False)) == 5
    assert columns(ReportOptions(term_ci=False), "impact") == 5
    assert columns(ReportOptions(requirements=False)) == 5
    assert columns(ReportOptions(requirements=False, term_c=False, term_ctr=False)) == 3
    assert columns(ReportOptions(requirements=False, term_ci=False), "impact") == 3
    # the widths always fill the page exactly
    t = _overview_table(air, "airborne", p, ReportOptions(requirements=False), st)
    assert abs(sum(t._colWidths) / 2.8346456692913385 - 174) < 0.01
    # a requirement on DnT,w + C keeps the column C even when it is switched off
    p.airborne_basis, p.airborne[0].requirement = "wc", 54
    evs = evaluate_project(p)
    air = [evs[0]]
    assert columns(ReportOptions(term_c=False, term_ctr=False)) == 6


@needs_samples
def test_terms_in_the_detail_page_and_the_notes(tmp_path):
    p = project()
    _, _, full = build(p, tmp_path, name="f.pdf")
    _, _, bare = build(p, tmp_path, ReportOptions(term_c=False, term_ctr=False, term_ci=False,
                                                  date=DATE), name="b.pdf")
    assert "spectrumaanpassingsterm" in " ".join(full)
    assert "spectrumaanpassingsterm" not in " ".join(bare)                 # no term, no explanation
    assert "= 54 (\u22121; \u22124) dB" in full[4]                           # DnT,w (C; Ctr) = ...
    assert "= 54 dB" in bare[4] and "(\u22121; \u22124)" not in bare[4]      # DnT,w itself stays


@needs_samples
def test_sections_can_be_switched_off_one_by_one(tmp_path):
    p = project()
    p.report.equipment = "Calibrator type 4231"
    _, _, full = build(p, tmp_path, name="f.pdf")
    first = full[0]
    assert "2 metingen (1 luchtgeluid, 1 contactgeluid)" in first and "Opmerkingen" in first
    assert "Apparatuur" in first and "Toelichting" in first
    for key, gone in (("summary", "2 metingen (1 luchtgeluid"), ("remarks", "Furnished."),
                      ("equipment", "Apparatuur"), ("notes", "Toelichting")):
        _, _, pages = build(p, tmp_path, ReportOptions(**{key: False}, date=DATE),
                            name=f"{key}.pdf")
        assert gone not in pages[0], key
        for other, still in (("summary", "2 metingen (1 luchtgeluid"), ("remarks", "Furnished."),
                             ("equipment", "Apparatuur"), ("notes", "Toelichting")):
            if other != key:
                assert still in pages[0], (key, other)


@needs_samples
def test_limit_bands_note_only_claims_no_effect_when_the_check_is_reliable(tmp_path):
    p = project()
    evs = evaluate_project(p)
    limit = [e for e in evs if e.ok and e.result.n_limit]
    if not limit:
        pytest.skip("the sample files have no band close to the background")
    neutral = "Ze kunnen het luchtgeluidresultaat te laag"
    claim = "niet be\u00efnvloed"
    _, _, off = build(p, tmp_path, ReportOptions(requirements=False, date=DATE), name="off.pdf")
    assert neutral in " ".join(off) and claim not in " ".join(off)         # nothing is claimed
    _, _, on = build(p, tmp_path, name="on.pdf")
    reliable = all(e.check.status in ("complies", "fails") for e in limit)
    if any(e.check.status == "inconclusive" for e in evs):
        assert "Niet conclusief:" in " ".join(on)
    else:
        assert (claim in " ".join(on)) is reliable and (neutral in " ".join(on)) is not reliable


def _fake(status, requirement, n_limit=2, kind="airborne"):
    from types import SimpleNamespace as NS
    return NS(kind=kind, ok=True, requirement=requirement, check=NS(status=status),
              uncertainty=None, tolerance=0,
              result=NS(n_limit=n_limit, names={"receiver": ["B.SVL"], "background": ["C.SVL"]}))


def _note_texts(evs, options):
    from export.pdf_report import _notes, styles
    return " ".join(getattr(f, "text", "") for f in _notes(evs, Project(name="x"), options, styles()))


def test_note_about_bands_close_to_the_background_makes_no_claim_it_cannot_back_up():
    claim, neutral, doubt = "niet be\u00efnvloed", "Ze kunnen het luchtgeluidresultaat", "Niet conclusief:"
    on = ReportOptions()
    # a reliable pass or fail: the result was not changed by the limit bands
    assert claim in _note_texts([_fake("complies", 50), _fake("fails", 60)], on)
    # no requirement to check against, so nothing can be said about the effect: neutral wording
    text = _note_texts([_fake("complies", 50), _fake("none", None)], on)
    assert neutral in text and claim not in text
    # a failure that could change: the full explanation
    text = _note_texts([_fake("inconclusive", 60)], on)
    assert doubt in text and claim not in text
    # requirements switched off: only the neutral wording, never a statement about compliance
    off = ReportOptions(requirements=False)
    for evs in ([_fake("complies", 50)], [_fake("inconclusive", 60)]):
        text = _note_texts(evs, off)
        assert neutral in text and claim not in text and doubt not in text and "marge" not in text
    # nothing close to the background: no note at all
    assert "dicht bij het achtergrondgeluiddrukniveau" not in _note_texts([_fake("complies", 50, 0)], on)
