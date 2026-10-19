"""In-situ tolerance of NBN S 01-400-1:2022 (5.4, 6.4, 8.4) in the requirement check."""
import dataclasses
import datetime as dt
from pathlib import Path

import pytest

from calc.building import (AirborneSituation, ImpactSituation, Project, Room, evaluate_project,
                           project_from_dict, project_to_dict)
from calc.examples import example_airborne
from calc.nbn import in_situ_tolerance, is_small_room


def test_tolerance_per_kind_and_room():
    assert in_situ_tolerance("airborne") == 2
    assert in_situ_tolerance("impact") == 2
    assert in_situ_tolerance("installation") == 1
    assert in_situ_tolerance("airborne", 20.0) == 4                  # < 25 m3
    assert in_situ_tolerance("installation", 20.0) == 3
    assert in_situ_tolerance("impact", 20.0, bedroom=True) == 2      # bedrooms excluded
    assert in_situ_tolerance("airborne", 25.0) == 2                  # 25 m3 is not smaller
    assert in_situ_tolerance("airborne", None) == 2                  # unknown: normal tolerance
    assert is_small_room(24.9, False) and not is_small_room(24.9, True)


def test_check_within_tolerance_is_its_own_pass():
    ev = example_airborne()                     # DnT,w compared with the requirement
    value = ev.assessed
    strict = dataclasses.replace(ev, requirement=value + 1)
    assert strict.check.status == "fails" and not strict.check.passed
    tol = dataclasses.replace(ev, requirement=value + 2, tolerance=2)
    assert (tol.check.status, tol.check.margin) == ("tolerance", -2) and tol.check.passed
    assert dataclasses.replace(ev, requirement=value + 3, tolerance=2).check.status == "fails"
    assert dataclasses.replace(ev, requirement=value, tolerance=2).check.status == "complies"


def test_project_file_keeps_volume_bedroom_and_switch(tmp_path):
    p = Project(rooms=[Room("A", volume=18.5, bedroom=True), Room("B")], nbn_tolerance=False)
    back = project_from_dict(project_to_dict(p, tmp_path), tmp_path)
    assert (back.rooms[0].volume, back.rooms[0].bedroom) == (18.5, True)
    assert (back.rooms[1].volume, back.rooms[1].bedroom) == (None, False)
    assert back.nbn_tolerance is False
    d = project_to_dict(p, tmp_path)
    del d["nbn_tolerance"]                      # an older project file: the Belgian rule
    d["rooms"][0]["volume_m3"] = "?"            # not a number: unknown
    back = project_from_dict(d, tmp_path)
    assert back.nbn_tolerance is True and back.rooms[0].volume is None


S = Path(__file__).parent.parent / "samples"
NEED = ["luchtgeluid_bron_L2.SVL", "luchtgeluid_ontvangst_L2.SVL", "contactgeluid_L4.SVL",
        "ontvangstruimte_BG_L20.SVL", "ontvangstruimte_RT_L11.SVL"]
needs_samples = pytest.mark.skipif(not all((S / n).exists() for n in NEED),
                                   reason="sample files missing")


def project(volume=None, bedroom=False, nbn=True) -> Project:
    p = Project(name="NBN", background_files=[str(S / "ontvangstruimte_BG_L20.SVL")],
                nbn_tolerance=nbn)
    p.rooms = [Room("A"), Room("B", [str(S / "ontvangstruimte_RT_L11.SVL")], volume=volume,
                                bedroom=bedroom)]
    # DnT,w = 54 and L'nT,w = 44 for these samples (see test_pdf_report)
    p.airborne = [AirborneSituation("A", "B", [str(S / "luchtgeluid_bron_L2.SVL")],
                                    [str(S / "luchtgeluid_ontvangst_L2.SVL")], requirement=57)]
    p.impact = [ImpactSituation("B", [str(S / "contactgeluid_L4.SVL")], "A", requirement=41)]
    return p


@needs_samples
def test_building_uses_the_tolerance_of_the_receiving_room():
    a, i = evaluate_project(project())                       # 54 vs 57, 44 vs 41: 3 dB worse
    assert (a.tolerance, a.check.status) == (2, "fails")
    assert (i.tolerance, i.check.status) == (2, "fails")
    a, i = evaluate_project(project(volume=20.0))             # small room: 4 dB
    assert (a.check.status, a.small_room) == ("tolerance", True)
    assert i.check.status == "tolerance"
    a, _ = evaluate_project(project(volume=20.0, bedroom=True))
    assert a.check.status == "fails"
    a, _ = evaluate_project(project(volume=20.0, nbn=False))  # switched off: strict
    assert (a.tolerance, a.check.status) == (0, "fails")


@needs_samples
def test_report_names_the_tolerance(tmp_path):
    pypdf = pytest.importorskip("pypdf")
    pytest.importorskip("reportlab")
    from export.pdf_report import ReportOptions, build_pdf_report

    def text(p, name):
        out = build_pdf_report(p, evaluate_project(p), tmp_path / name,
                               ReportOptions(date=dt.date(2026, 10, 1)))
        return " ".join(" ".join(pg.extract_text().split())
                        for pg in pypdf.PdfReader(str(out)).pages)

    on = text(project(volume=20.0), "on.pdf")
    assert "Voldoet binnen tolerantie" in on and "NBN S 01-400-1:2022 (5.4, 6.4 en 8.4)" in on
    assert "tolerantie 4 dB (ruimte < 25 m" in on
    assert "2 voldoen (waarvan 2 binnen de tolerantie)" in on
    off = text(project(volume=20.0, nbn=False), "off.pdf")
    assert "binnen tolerantie" not in off and "NBN S 01-400-1:2022 (5.4" not in off
