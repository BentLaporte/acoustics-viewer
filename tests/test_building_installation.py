"""Installation noise in a building project: names, evaluation, requirements, saving, CLI."""
import csv
import io
import json
from pathlib import Path

import pytest

from calc import cli
from calc.building import (INTEGRATED_NOTE, AirborneSituation, InstallationSituation, Project,
                           Room, equipment_used, evaluate_project, load_project, save_project,
                           situation_name)
from calc.installation import Recording
from helpers import make_variant

S = Path(__file__).parent.parent / "samples"
L22, BG = S / "installatiegeluid_L22.SVL", S / "installatiegeluid_BG_L39.SVL"
RT = [S / "installatiegeluid_RT_L15.SVL", S / "installatiegeluid_RT_L16.SVL"]
needs_samples = pytest.mark.skipif(not all(p.exists() for p in [L22, BG, *RT]),
                                   reason="installation noise sample files not present")


def project(bg=True, **kw) -> Project:
    room = Room("Slaapkamer 1", [str(p) for p in RT], [str(BG)] if bg else [])
    s = InstallationSituation("Slaapkamer 1", [Recording(L22)], comment="warmtepomp", **kw)
    return Project(name="Test", rooms=[room, Room("Technische ruimte")], installation=[s])


def test_names():
    assert situation_name("installation", "", "Slaapkamer 1", "warmtepomp") == \
        "installation in Slaapkamer 1 (warmtepomp)"
    assert situation_name("installation", "Technische ruimte", "Slaapkamer 1") == \
        "installation Technische ruimte to Slaapkamer 1"
    assert situation_name("impact", "", "B") == "impact to B"          # unchanged


def test_installation_comes_after_airborne_and_impact_in_the_names():
    p = project()
    p.airborne.append(AirborneSituation("Technische ruimte", "Slaapkamer 1"))
    assert p.situation_names() == ["airborne Technische ruimte to Slaapkamer 1",
                                   "installation in Slaapkamer 1 (warmtepomp)"]


@needs_samples
def test_evaluation():
    (ev,) = evaluate_project(project(requirement=44))
    assert ev.ok and ev.kind == "installation" and ev.basis_label == "LAeq,nT"
    assert ev.value == 44 and ev.assessed == 44 and ev.rating is None and ev.curve is None
    assert ev.check.status == "complies" and ev.check.margin == 0
    assert ev.notes == [INTEGRATED_NOTE, "T20 used at 400, 500, 630 Hz (no T30)"]
    assert ("SV 977D", 156226, ("level", "background", "rt")) in equipment_used([ev])


@needs_samples
def test_lafmax_and_requirement_fails():
    (ev,) = evaluate_project(project(requirement=40, quantity="lafmax"))
    assert ev.basis_label == "LAFmax,nT" and ev.value == 46
    assert ev.check.status == "fails" and ev.check.margin == -6


@needs_samples
def test_failure_close_to_the_background_is_inconclusive(tmp_path):
    # 36 dB, 3.5 dB above the background; with the background subtracted at least 33 dB
    p = project(requirement=33)                       # + 1 dB tolerance: 33 could comply
    p.installation[0].recordings = [Recording(make_variant(L22, tmp_path / "q.SVL", -8.0))]
    (ev,) = evaluate_project(p)
    assert ev.value == 36 and ev.check.status == "inconclusive"
    assert "within 6 dB of background (value overestimated)" in ev.notes
    p.installation[0].requirement = 30                # 33 > 30 + 1: fails whatever the background
    (ev,) = evaluate_project(p)
    assert ev.check.status == "fails"


@needs_samples
def test_background_is_optional():
    (ev,) = evaluate_project(project(bg=False))
    assert ev.ok and "background not checked" in ev.notes


@needs_samples
def test_time_window_is_used():
    p = project(quantity="lafmax")
    p.installation[0].recordings = [Recording(L22, 2, 8)]
    (ev,) = evaluate_project(p)
    assert ev.result.levels[0] == pytest.approx(45.94)


def test_errors_do_not_stop_the_rest():
    p = project()
    p.rooms[0].rt_files = []
    p.installation.append(InstallationSituation("Nowhere"))
    a, b = evaluate_project(p)
    assert not a.ok and "reverberation time files for room 'Slaapkamer 1'" in a.error
    assert not b.ok and "room 'Nowhere' does not exist" in b.error
    assert a.value is None and a.check.status == "none"


def test_save_and_load_keep_windows_and_settings(tmp_path):
    p = project(requirement=30, quantity="lafmax", method="positions",
                source_room="Technische ruimte")
    p.installation[0].recordings = [Recording(L22, 5, 35), Recording(L22, 40, None)]
    path = tmp_path / "job.json"
    save_project(p, path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    rec = raw["installation"][0]["recordings"]
    assert [(r["start_s"], r["end_s"]) for r in rec] == [(5, 35), (40, None)]
    assert raw["schema"] == 2
    q = load_project(path).installation[0]
    assert (q.quantity, q.method, q.requirement, q.source_room, q.comment) == \
        ("lafmax", "positions", 30, "Technische ruimte", "warmtepomp")
    assert [(r.path, r.start, r.end) for r in q.recordings] == \
        [(L22.resolve(), 5, 35), (L22.resolve(), 40, None)]


def test_project_without_installation_is_saved_as_before(tmp_path):
    p = Project(name="Old")
    save_project(p, tmp_path / "old.json")
    assert "installation" not in json.loads((tmp_path / "old.json").read_text(encoding="utf-8"))
    assert load_project(tmp_path / "old.json").installation == []


@needs_samples
def test_cli_building_with_installation(tmp_path, capsys):
    path = tmp_path / "job.json"
    save_project(project(requirement=40), path)
    assert cli.main(["building", str(path), "--format", "json"]) == 0
    d = json.loads(capsys.readouterr().out)
    (m,) = d["measurements"]
    assert m["kind"] == "installation" and m["result"]["single_number_db"] == 44
    assert m["requirement"]["check"] == "fails" and m["receiver_room"] == "Slaapkamer 1"
    assert d["summary"]["fails"] == 1
    assert cli.main(["building", str(path)]) == 0
    out = capsys.readouterr().out
    assert "installation in Slaapkamer 1 (warmtepomp)" in out and "LAeq,nT" in out
    assert cli.main(["building", str(path), "--format", "csv"]) == 0
    row = next(csv.DictReader(io.StringIO(capsys.readouterr().out)))
    assert row["single_number_db"] == "44" and row["quantity"] == "LAeq,nT"
