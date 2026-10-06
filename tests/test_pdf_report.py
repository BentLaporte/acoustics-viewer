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
NEED = ["A_L2.SVL", "B_L2.SVL", "B_L4.SVL", "C_L20.SVL", "B_L11.SVL"]
needs_samples = pytest.mark.skipif(not all((S / n).exists() for n in NEED),
                                   reason="sample files missing")
DATE = dt.date(2026, 9, 30)


def f(n):
    return str(S / n)


def project() -> Project:
    p = Project(name="Test building", background_files=[f("C_L20.SVL")])
    p.rooms = [Room("A"), Room("B", [f("B_L11.SVL")])]
    p.airborne = [AirborneSituation("A", "B", [f("A_L2.SVL")], [f("B_L2.SVL")], "wall", 54)]
    p.impact = [ImpactSituation("B", [f("B_L4.SVL")], "A", "carpet", 40)]
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
    for text in ("Sound insulation measurements", "Test building", "Client Ltd", "Main Street 1",
                 "J. Doe", "30 September 2026", "Furnished.", "Doors closed.",
                 "airborne", "Complies", "Does not comply", "2 measurement(s)"):
        assert text in first, text
    assert "1 comply" in first and "1 do not comply" in first
    assert "A \u2192 B (wall)" in first and "A \u2192 B (carpet)" in first
    assert "Comparison" in pages[1]
    assert "per band" in pages[2] and "per band" in pages[3]
    assert "airborne A to B (wall)" in pages[4] and "impact A to B (carpet)" in pages[5]
    assert "A_L2.SVL" in pages[4] and "B_L4.SVL" in pages[5]                # file names only
    assert str(S) not in "".join(pages)                                      # no full paths
    assert "Page 6 of 6" in pages[5] and "Page 1 of 6" in first
    assert reader.metadata.title == "Test building - sound insulation measurements"
    assert reader.metadata.author == "J. Doe"


@needs_samples
def test_values_in_the_report_match_the_calculation(tmp_path):
    p = project()
    _, _, pages = build(p, tmp_path)
    a, i = evaluate_project(p)
    assert (a.value, i.value) == (54, 44)
    assert "54" in pages[4] and "\u22121" in pages[4]                        # DnT,w and C
    assert "+0 dB" in pages[0] and "\u22124 dB" in pages[0]                  # margins 54/54, 40/44
    assert "67.5" in pages[4]                                                # DnT at 3150 Hz


@needs_samples
def test_options_and_hidden(tmp_path):
    p = project()
    _, _, pages = build(p, tmp_path, ReportOptions(per_measurement_pages=False, date=DATE),
                        name="a.pdf")
    assert len(pages) == 4
    full, _, _ = build(p, tmp_path, name="b.pdf")
    _, _, no_bands = build(p, tmp_path, ReportOptions(per_band_tables=False, date=DATE),
                           name="c.pdf")
    assert "bands close to the background are shaded" in " ".join(read(full)[1])
    assert "bands close to the background are shaded" not in " ".join(no_bands)
    # measurements unticked in the viewer are left out completely
    _, _, pages = build(p, tmp_path, hidden={("impact", "impact A to B (carpet)")}, name="d.pdf")
    joined = " ".join(pages)
    assert "carpet" not in joined and len(pages) == 4        # overview, comparison, curves, detail
    assert "1 measurement(s)" in pages[0]


@needs_samples
def test_problem_measurements_are_reported_not_fatal(tmp_path):
    p = project()
    p.airborne.append(AirborneSituation("A", "B", [f("A_L2.SVL")], [str(S / "missing.SVL")],
                                        "missing file"))
    p.rt_kind = "t30"
    _, _, pages = build(p, tmp_path)
    assert "file not found: missing.SVL" in pages[0]
    assert len(pages) == 6                                   # the failed one has no own page
    p2 = project()
    p2.rt_kind = "edt"                                       # no rating possible
    _, _, pages2 = build(p2, tmp_path, name="edt.pdf")
    assert "reverberation time missing" in pages2[0] and "Rating not possible" in " ".join(pages2)


@needs_samples
def test_special_characters_in_names_and_text(tmp_path):
    p = project()
    p.rooms += [Room("Caf\u00e9 <1> & Co")]
    p.airborne.append(AirborneSituation("Caf\u00e9 <1> & Co", "B", [f("A_L2.SVL")],
                                        [f("B_L2.SVL")], "\u2265 & <b>bold</b>"))
    p.report.remarks = "Line with <tags> & ampersand \u2192 arrow"
    _, _, pages = build(p, tmp_path)
    joined = " ".join(pages)
    assert "Caf\u00e9 <1> & Co" in joined and "<b>bold</b>" in joined
    assert "Line with <tags> & ampersand \u2192 arrow" in pages[0]


@needs_samples
def test_many_measurements_paginate(tmp_path):
    p = project()
    for k in range(25):
        p.airborne.append(AirborneSituation("A", "B", [f("A_L2.SVL")], [f("B_L2.SVL")],
                                            f"position {k}"))
        p.impact.append(ImpactSituation("B", [f("B_L4.SVL")], "A", f"position {k}"))
    _, reader, pages = build(p, tmp_path, ReportOptions(per_measurement_pages=False, date=DATE))
    assert len(pages) > 6                                   # tables and charts flow over pages
    assert "position 24" in " ".join(pages)
    assert f"Page {len(pages)} of {len(pages)}" in pages[-1]


def test_empty_building(tmp_path):
    out = build_pdf_report(Project(name="Empty"), [], tmp_path / "e.pdf",
                           ReportOptions(date=DATE))
    _, pages = read(out)
    assert len(pages) == 1 and "There are no measurements" in pages[0]


def test_default_name_is_a_valid_file_name():
    assert default_report_name(Project(name='Site: A/B "x"?')) == "Site AB x - report.pdf"
    assert default_report_name(Project(name="  ")) == "Building - report.pdf"


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
    assert len(pages) == 7 and pages[1].startswith("Rooms")
    text = pages[1]
    assert "Source room, seen from the door" in text and "Receiving room" in text
    assert "Never mentioned" not in " ".join(pages)                     # room not used by a measurement
    assert "Source room in 1 measurement, tapping room in 1 measurement" in text   # room A
    assert "Receiving room in 2 measurements" in text                              # room B
    # pictures per page: overview 0, rooms 3 (2 of A + 1 of B), bar charts 2, curves 1 + 1,
    # measurement pages 3 (main photo of both rooms + the rating chart)
    assert images_per_page(reader) == [0, 3, 2, 1, 1, 3, 3]
    assert "Source room: A" in pages[5] and "Receiving room: B" in pages[5]
    assert "Tapping room: A" in pages[6]
    assert "Source room, seen from the door" in pages[5]                # caption of the main photo
    assert out.stat().st_size < 1_000_000                               # 4000x3000 photo shrunk


@needs_samples
def test_photos_can_be_left_out(tmp_path):
    p = with_photos(tmp_path)
    _, reader, pages = build(p, tmp_path, ReportOptions(room_photos=False, date=DATE))
    assert len(pages) == 6 and not any(p.startswith("Rooms") for p in pages)
    assert images_per_page(reader) == [0, 2, 1, 1, 1, 1]                # only the charts remain
    assert "Source room, seen from the door" not in " ".join(pages)
    # rooms without photos: no photo page and no strips
    plain = project()
    _, reader2, pages2 = build(plain, tmp_path, name="plain.pdf")
    assert len(pages2) == 6 and "Rooms" not in pages2[1][:10]
    assert "Source room: A" not in " ".join(pages2)


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
    assert "Photo could not be read: broken.jpg" in pages[1]
    assert "Photo could not be read: gone.jpg" in pages[1]
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
    assert "Receiving room: B" in page and "B photo" in page            # the strip is still made
    assert "Source room: A" in page                                     # name without picture
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
    assert "Measurement files (date and time of the measurement)" in airborne
    # airborne: source A_L2 12:11, receiver B_L2 12:16, background 28/09 11:40, RT 12:44
    assert "A_L2.SVL (22/09/2026 12:11)" in airborne
    assert "B_L2.SVL (22/09/2026 12:16)" in airborne
    assert "C_L20.SVL (28/09/2026 11:40)" in airborne            # another day: visible in the report
    assert "B_L11.SVL (22/09/2026 12:44)" in airborne
    assert "B_L4.SVL (22/09/2026 12:19)" in impact and "C_L20.SVL (28/09/2026 11:40)" in impact
    assert str(S) not in airborne                                  # still no folders


@needs_samples
def test_several_files_per_role_are_listed_each_with_its_time(tmp_path):
    p = project()
    p.airborne[0].receiver_files = [f("B_L2.SVL"), f("B_L4.SVL")]
    _, _, pages = build(p, tmp_path)
    page = pages[4]
    assert "B_L2.SVL (22/09/2026 12:16)" in page and "B_L4.SVL (22/09/2026 12:19)" in page


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
    assert "A_L2.SVL" in text and "(22/09/2026" not in text


# ------------------------------------------------------------------ equipment, optional dates
@needs_samples
def test_equipment_section_lists_the_instruments_and_what_they_measured(tmp_path):
    p = project()
    p.report.equipment = "Calibrator type 4231\nTapping machine Norsonic"
    _, _, pages = build(p, tmp_path)
    first = pages[0]
    assert "Equipment" in first and "Instrument Serial number Used for" in first
    # A_L2 is from the instrument with serial 99942 (source room); B_L2/B_L4/C_L20/B_L11 from 156226
    assert "SV 977D 99942 source room levels" in first
    assert "SV 977D 156226 receiving room levels, tapping machine levels, background, reverberation time" in first
    assert "\u2022 Calibrator type 4231" in first and "\u2022 Tapping machine Norsonic" in first


@needs_samples
def test_equipment_only_counts_included_measurements(tmp_path):
    p = project()
    hidden = {("airborne", "airborne A to B (wall)")}                 # the only one using A_L2
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
    assert "Equipment" not in first
    p.report.equipment = "Only free text"
    out = build_pdf_report(p, ev, tmp_path / "t.pdf", ReportOptions(date=DATE))
    first = read(out)[1][0]
    assert "Equipment" in first and "Only free text" in first and "Serial number" not in first


@needs_samples
def test_file_dates_are_optional(tmp_path):
    p = project()
    _, _, with_dates = build(p, tmp_path, ReportOptions(date=DATE), name="a.pdf")
    _, _, no_dates = build(p, tmp_path, ReportOptions(file_dates=False, date=DATE), name="b.pdf")
    assert "A_L2.SVL (22/09/2026 12:11)" in with_dates[4]
    assert "Measurement files (date and time of the measurement)" in with_dates[4]
    assert "22/09/2026" not in no_dates[4] and "28/09/2026" not in no_dates[4]
    assert "A_L2.SVL" in no_dates[4] and "Measurement files" in no_dates[4]
    assert "date and time" not in no_dates[4]
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
