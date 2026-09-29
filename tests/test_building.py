"""Building model: several rooms and measurements evaluated side by side."""
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from calc.building import (AirborneSituation, ImpactSituation, Project, Room, evaluate_project,
                           load_project, natural_key, save_project, situation_name)
from helpers import make_variant

S = Path(__file__).parent.parent / "samples"
NEED = ["A_L2.SVL", "B_L2.SVL", "B_L4.SVL", "C_L20.SVL", "B_L11.SVL"]
needs_samples = pytest.mark.skipif(not all((S / n).exists() for n in NEED),
                                   reason="sample files missing")


def f(name):
    return str(S / name)


def basic_project() -> Project:
    p = Project(name="Test", background_files=[f("C_L20.SVL")])
    p.rooms = [Room("A"), Room("B", rt_files=[f("B_L11.SVL")])]
    p.airborne = [AirborneSituation("A", "B", [f("A_L2.SVL")], [f("B_L2.SVL")])]
    p.impact = [ImpactSituation("B", [f("B_L4.SVL")], tapping_room="A", comment="carpet")]
    return p


# ------------------------------------------------------------------ names and sorting
def test_automatic_names_follow_the_template():
    assert situation_name("airborne", "0.1.04 Bedroom", "0.1.03 Dining") == \
        "airborne 0.1.04 Bedroom to 0.1.03 Dining"
    assert situation_name("impact", "0.2.03", "B.1.02", "carpet") == "impact 0.2.03 to B.1.02 (carpet)"
    assert situation_name("impact", "", "B.1.02", "  tile ") == "impact to B.1.02 (tile)"
    assert situation_name("airborne", "A", "B", "   ") == "airborne A to B"


def test_natural_sort_of_rooms():
    names = ["B.G.02 Sas", "0.2.02 Living", "B.1.05 Bed", "0.1.03 Dining", "0.10.01 Hall",
             "1.2.02 Living", "b.1.04 bed", "0.1.04 Bed", "B.1.02 Living"]
    assert sorted(names, key=natural_key) == [
        "0.1.03 Dining", "0.1.04 Bed", "0.2.02 Living", "0.10.01 Hall", "1.2.02 Living",
        "B.1.02 Living", "b.1.04 bed", "B.1.05 Bed", "B.G.02 Sas"]


def test_room_sort_puts_numbers_before_letters():
    p = Project(rooms=[Room(n) for n in ["Attic", "3 Hall", "10 Hall", "Zoo"]])
    p.sort_rooms()
    assert [r.name for r in p.rooms] == ["3 Hall", "10 Hall", "Attic", "Zoo"]


def test_duplicate_names_get_a_counter():
    p = Project()
    p.airborne = [AirborneSituation("A", "B"), AirborneSituation("A", "B"),
                  AirborneSituation("A", "B", comment="door open")]
    p.impact = [ImpactSituation("B", tapping_room="A"), ImpactSituation("B", tapping_room="A")]
    assert p.situation_names() == ["airborne A to B", "airborne A to B #2",
                                   "airborne A to B (door open)",
                                   "impact A to B", "impact A to B #2"]


# ------------------------------------------------------------------ evaluation
@needs_samples
def test_evaluate_matches_single_measurements():
    ev = evaluate_project(basic_project())
    assert [e.kind for e in ev] == ["airborne", "impact"]
    a, i = ev
    assert a.name == "airborne A to B" and i.name == "impact A to B (carpet)"
    assert a.ok and (a.value, a.result.c, a.result.ctr) == (54, -1, -4)
    assert i.ok and (i.value, i.result.ci) == (44, -1) and i.comment == "carpet"
    assert a.receiver_room == "B" and i.source_room == "A" and a.notes == []
    assert len(a.curve) == 16 and len(i.curve) == 16


@needs_samples
def test_room_background_overrides_building_background(tmp_path):
    loud = make_variant(S / "C_L20.SVL", tmp_path / "loud_bg.SVL", 30.0)
    p = basic_project()
    plain = evaluate_project(p)[0]
    p.rooms[1].background_files = [str(loud)]                # room B gets its own background
    own = evaluate_project(p)[0]
    assert plain.result.n_limit == 0 and own.result.n_limit > 0
    assert any("within 6 dB" in n for n in own.notes)
    assert own.result.dnt.tolist() != plain.result.dnt.tolist()


@needs_samples
def test_two_receiver_rooms_are_independent(tmp_path):
    quieter = make_variant(S / "B_L2.SVL", tmp_path / "C_recv.SVL", -3.0)   # 3 dB lower level
    p = basic_project()
    p.rooms.append(Room("C", rt_files=[f("B_L11.SVL")]))
    p.airborne.append(AirborneSituation("A", "C", [f("A_L2.SVL")], [str(quieter)]))
    ab, ac = evaluate_project(p)[:2]
    assert ab.name == "airborne A to B" and ac.name == "airborne A to C"
    # 3 dB lower receiver level -> DnT exactly 3 dB higher in every band (no correction needed)
    assert np.allclose(ac.curve - ab.curve, 3.0, atol=0.02)
    assert ac.value > ab.value


@needs_samples
def test_errors_are_reported_per_measurement():
    p = basic_project()
    p.rooms.append(Room("NoRT"))
    p.airborne += [
        AirborneSituation("A", "NoRT", [f("A_L2.SVL")], [f("B_L2.SVL")]),
        AirborneSituation("A", "Ghost", [f("A_L2.SVL")], [f("B_L2.SVL")]),
        AirborneSituation("A", "B", [f("A_L2.SVL")], [str(S / "does_not_exist.SVL")],
                          "missing file"),
        AirborneSituation("A", "B", [], [f("B_L2.SVL")], "no source files")]
    p.impact.append(ImpactSituation("B", [f("A_L2.SVL"), str(S / "README.md")], "A", "bad"))
    ev = {e.name: e for e in evaluate_project(p)}
    assert ev["airborne A to B"].ok and ev["impact A to B (carpet)"].ok      # untouched
    assert "reverberation time files for room 'NoRT'" in ev["airborne A to NoRT"].error
    assert "'Ghost' does not exist" in ev["airborne A to Ghost"].error
    assert ev["airborne A to B (missing file)"].error == "file not found: does_not_exist.SVL"
    assert "no source room level files" in ev["airborne A to B (no source files)"].error
    assert ev["impact A to B (bad)"].error and not ev["impact A to B (bad)"].ok
    assert ev["airborne A to NoRT"].notes == [ev["airborne A to NoRT"].error]


@needs_samples
def test_rt_kind_and_missing_rt_band_note():
    p = basic_project()
    p.rt_kind = "edt"                                                  # EDT missing at 100 Hz
    a = evaluate_project(p)[0]
    assert a.ok and a.rating is None and a.value is None
    assert any("reverberation time missing at 100" in n for n in a.notes)


@needs_samples
def test_averaging_note():
    p = basic_project()
    p.airborne[0].receiver_files = [f("B_L2.SVL"), f("B_L2.SVL")]
    assert "averaged over several files" in evaluate_project(p)[0].notes


# ------------------------------------------------------------------ project files
@needs_samples
def test_save_and_load_roundtrip_with_relative_paths(tmp_path):
    proj_dir = tmp_path / "job"
    data = proj_dir / "data"
    data.mkdir(parents=True)
    for n in NEED:
        shutil.copy(S / n, data / n)
    p = Project(name="Job", background_files=[str(data / "C_L20.SVL")], rt_kind="t20")
    p.rooms = [Room("B", [str(data / "B_L11.SVL")]), Room("A")]              # deliberately unsorted
    p.airborne = [AirborneSituation("A", "B", [str(data / "A_L2.SVL")],
                                    [str(data / "B_L2.SVL")], "wall")]
    p.impact = [ImpactSituation("B", [str(data / "B_L4.SVL")], "A", "tile")]
    path = proj_dir / "job.json"
    save_project(p, path)
    raw = json.loads(path.read_text())
    assert raw["schema"] == 2 and "name" not in raw["airborne"][0]
    assert raw["airborne"][0]["comment"] == "wall" and raw["impact"][0]["comment"] == "tile"
    assert raw["background_files"] == ["data/C_L20.SVL"]               # stored relative, portable
    assert [r["name"] for r in raw["rooms"]] == ["A", "B"]             # saved in sorted order
    assert raw["rooms"][1]["rt_files"] == ["data/B_L11.SVL"]
    q = load_project(path)
    assert (q.name, q.rt_kind, [r.name for r in q.rooms]) == ("Job", "t20", ["A", "B"])
    assert Path(q.rooms[1].rt_files[0]) == (data / "B_L11.SVL").resolve()
    assert (q.airborne[0].comment, q.impact[0].comment, q.impact[0].tapping_room) == \
        ("wall", "tile", "A")
    before = [(e.name, e.value, e.error) for e in evaluate_project(q)]
    # move the whole folder: relative paths keep the project working
    moved = tmp_path / "moved"
    shutil.move(str(proj_dir), str(moved))
    after = [(e.name, e.value, e.error) for e in evaluate_project(load_project(moved / "job.json"))]
    assert before == after and all(err is None for _, _, err in after)
    assert [n for n, _, _ in after] == ["airborne A to B (wall)", "impact A to B (tile)"]


def test_schema1_projects_are_migrated(tmp_path):
    """Files from before the automatic names: a trailing '(...)' of the old name is the comment."""
    old = {
        "schema": 1, "name": "Old", "rt_kind": "t30", "background_files": [],
        "rooms": [{"name": "B.1.02 Living", "rt_files": [], "background_files": []},
                  {"name": "0.2.03 Kitchen", "rt_files": [], "background_files": []}],
        "airborne": [{"name": "Wall between 0.2.03 and B.1.02 (mostly via door)",
                      "source_room": "0.2.03 Kitchen", "receiver_room": "B.1.02 Living",
                      "source_files": [], "receiver_files": []},
                     {"name": "Floor between 0.2.03 and B.1.02", "source_room": "0.2.03 Kitchen",
                      "receiver_room": "B.1.02 Living", "source_files": [], "receiver_files": []}],
        "impact": [{"name": "Floor between 0.2.03 and B.1.02 (carpet)", "receiver_room": "B.1.02 Living",
                    "tapping_room": "0.2.03 Kitchen", "tapping_files": []}]}
    path = tmp_path / "old.json"
    path.write_text(json.dumps(old))
    p = load_project(path)
    assert [r.name for r in p.rooms] == ["0.2.03 Kitchen", "B.1.02 Living"]     # sorted on load
    assert p.situation_names() == [
        "airborne 0.2.03 Kitchen to B.1.02 Living (mostly via door)",
        "airborne 0.2.03 Kitchen to B.1.02 Living",
        "impact 0.2.03 Kitchen to B.1.02 Living (carpet)"]


def test_load_rejects_unknown_schema(tmp_path):
    path = tmp_path / "x.json"
    path.write_text(json.dumps({"schema": 99}))
    with pytest.raises(ValueError):
        load_project(path)


# ------------------------------------------------------------------ requirements
@needs_samples
def test_requirement_check_airborne_and_impact():
    p = basic_project()                                   # airborne 54 (C -1, Ctr -4), impact 44 (CI -1)
    a, i = p.airborne[0], p.impact[0]
    a.requirement, i.requirement = 50, 45
    ea, ei = evaluate_project(p)
    assert (ea.check.status, ea.check.margin) == ("complies", 4)          # 54 >= 50
    assert (ei.check.status, ei.check.margin) == ("complies", 1)          # 44 <= 45
    a.requirement, i.requirement = 54, 44                                 # exactly on the limit
    ea, ei = evaluate_project(p)
    assert (ea.check.status, ea.check.margin) == ("complies", 0)
    assert (ei.check.status, ei.check.margin) == ("complies", 0)
    a.requirement, i.requirement = 55, 43
    ea, ei = evaluate_project(p)
    assert (ea.check.status, ea.check.margin, ea.check.text) == ("fails", -1, "Does not comply")
    assert (ei.check.status, ei.check.margin) == ("fails", -1)
    a.requirement = i.requirement = None
    assert all(e.check.status == "none" and e.check.text == "" for e in evaluate_project(p))


@needs_samples
def test_requirement_basis_uses_adaptation_terms():
    p = basic_project()
    p.airborne[0].requirement, p.impact[0].requirement = 53, 43
    p.airborne_basis, p.impact_basis = "wc", "wci"             # 54 + (-1) = 53; 44 + (-1) = 43
    ea, ei = evaluate_project(p)
    assert (ea.assessed, ea.check.status, ea.check.margin, ea.basis_label) == \
        (53, "complies", 0, "DnT,w + C")
    assert (ei.assessed, ei.check.status, ei.check.margin, ei.basis_label) == \
        (43, "complies", 0, "L'nT,w + C_I")
    p.airborne_basis = "wctr"                                  # 54 + (-4) = 50 < 53
    assert evaluate_project(p)[0].assessed == 50
    assert evaluate_project(p)[0].check.status == "fails"


@needs_samples
def test_no_result_when_rating_impossible():
    p = basic_project()
    p.rt_kind = "edt"                                          # EDT missing at 100 Hz -> no rating
    p.airborne[0].requirement = 50
    e = evaluate_project(p)[0]
    assert e.assessed is None and e.check.status == "no_result"


@needs_samples
def test_limit_bands_make_a_failure_inconclusive_only_when_they_matter(tmp_path):
    band_3150 = 36                                              # position in the 45-band table
    loud_3150 = make_variant(S / "C_L20.SVL", tmp_path / "bg_3150.SVL", 60.0, only_bands=[band_3150])
    loud_all = make_variant(S / "C_L20.SVL", tmp_path / "bg_all.SVL", 40.0)

    # airborne: 3150 Hz is far above the curve, so a limit value there cannot change the rating
    p = basic_project()
    p.airborne[0].requirement = 60                              # not met (54)
    p.rooms[1].background_files = [str(loud_3150)]
    e = evaluate_project(p)[0]
    assert e.result.n_limit == 1 and e.check.status == "fails"          # sure: band is irrelevant
    p.airborne_basis = "wc"                                     # C uses all bands -> not sure
    p.airborne[0].requirement = 60
    assert evaluate_project(p)[0].check.status == "inconclusive"
    # a met requirement stays a sure pass, whatever the limit bands are
    p.airborne[0].requirement = 40
    assert evaluate_project(p)[0].check.status == "complies"
    # many limit bands, including ones below the curve -> failure is not conclusive
    p2 = basic_project()
    p2.airborne[0].requirement = 60
    p2.rooms[1].background_files = [str(loud_all)]
    assert evaluate_project(p2)[0].check.status == "inconclusive"

    # impact: 3150 Hz is outside the C_I range and far below the curve
    p3 = basic_project()
    p3.impact[0].requirement = 40                               # not met (44)
    p3.rooms[1].background_files = [str(loud_3150)]
    assert evaluate_project(p3)[1].check.status == "fails"          # [1]: impact follows airborne
    p3.impact_basis = "wci"                                     # w + C_I: 3150 Hz not used
    p3.impact[0].requirement = 39
    assert evaluate_project(p3)[1].check.status == "fails"
    p4 = basic_project()
    p4.impact[0].requirement = 40
    p4.rooms[1].background_files = [str(loud_all)]              # 100-2500 Hz affected too
    assert evaluate_project(p4)[1].check.status == "inconclusive"


@needs_samples
def test_requirement_and_basis_roundtrip(tmp_path):
    p = basic_project()
    p.airborne[0].requirement, p.impact[0].requirement = 54, 58
    p.airborne_basis, p.impact_basis = "wctr", "wci"
    path = tmp_path / "req.json"
    save_project(p, path)
    raw = json.loads(path.read_text())
    assert raw["airborne"][0]["requirement"] == 54 and raw["impact"][0]["requirement"] == 58
    assert (raw["airborne_basis"], raw["impact_basis"]) == ("wctr", "wci")
    q = load_project(path)
    assert (q.airborne[0].requirement, q.impact[0].requirement) == (54, 58)
    assert (q.airborne_basis, q.impact_basis) == ("wctr", "wci")


def test_old_files_without_requirement_load_with_defaults(tmp_path):
    old = {"schema": 2, "name": "X", "rt_kind": "t30", "background_files": [], "rooms": [],
           "airborne": [{"source_room": "A", "receiver_room": "B", "comment": "",
                         "source_files": [], "receiver_files": []}],
           "impact": [], "airborne_basis": "nonsense"}
    path = tmp_path / "x.json"
    path.write_text(json.dumps(old))
    q = load_project(path)
    assert q.airborne[0].requirement is None
    assert (q.airborne_basis, q.impact_basis) == ("w", "w")               # unknown value -> default
