"""The command line (python -m calc): output formats, requirement checks, exit status."""
import csv
import io
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from calc import cli
from calc.airborne import compute_airborne
from calc.building import (AirborneSituation, ImpactSituation, Project, Room, save_project)
from calc.examples import example_airborne
from calc.results import evaluated_to_dict

ROOT = Path(__file__).parent.parent
S = ROOT / "samples"
NEED = ["luchtgeluid_bron_L2.SVL", "luchtgeluid_ontvangst_L2.SVL", "contactgeluid_L4.SVL", "ontvangstruimte_BG_L20.SVL", "ontvangstruimte_RT_L11.SVL"]
needs_samples = pytest.mark.skipif(not all((S / n).exists() for n in NEED), reason="samples missing")


def strict_json(text):
    """Parse JSON and refuse NaN / Infinity tokens (they are not JSON)."""
    def bad(token):
        raise ValueError(f"not valid JSON: {token}")
    return json.loads(text, parse_constant=bad)


def run(capsys, *argv):
    code = cli.main([str(a) for a in argv])
    out = capsys.readouterr()
    return code, out.out, out.err


def air_args(*extra):
    return ["airborne", "--source", S / "luchtgeluid_bron_L2.SVL", "--receiver", S / "luchtgeluid_ontvangst_L2.SVL",
            "--background", S / "ontvangstruimte_BG_L20.SVL", "--rt", S / "ontvangstruimte_RT_L11.SVL", *extra]


def imp_args(*extra):
    return ["impact", "--tapping", S / "contactgeluid_L4.SVL", "--background", S / "ontvangstruimte_BG_L20.SVL",
            "--rt", S / "ontvangstruimte_RT_L11.SVL", *extra]


# ------------------------------------------------------------------ airborne / impact
@needs_samples
def test_airborne_text(capsys):
    code, out, err = run(capsys, *air_args("--requirement", "54"))
    assert code == 0 and err == ""
    assert "DnT,w = 54 dB   C = -1   Ctr = -4" in out
    assert "Reference curve shifted +2 dB; sum of unfavourable deviations 25.8 dB" in out
    assert "Requirement DnT,w at least 54 dB: Complies (+0 dB)" in out
    assert "luchtgeluid_bron_L2.SVL (22/09/2026 12:11, SV 977D #99942)" in out         # file, date, instrument
    assert str(S) not in out                                             # no folders


@needs_samples
def test_airborne_json_matches_the_calculation(capsys):
    code, out, _ = run(capsys, *air_args("--format", "json", "--requirement", "55"))
    d = strict_json(out)
    res = compute_airborne(S / "luchtgeluid_bron_L2.SVL", S / "luchtgeluid_ontvangst_L2.SVL", S / "ontvangstruimte_BG_L20.SVL", S / "ontvangstruimte_RT_L11.SVL")
    assert code == 0 and d["schema_version"] == 1 and d["kind"] == "airborne" and d["ok"]
    assert d["result"]["quantity"] == "DnT,w"
    assert (d["result"]["single_number_db"], d["result"]["C"], d["result"]["Ctr"]) == (54, -1, -4)
    assert d["requirement"] == {"compared_quantity": "DnT,w", "direction": ">=", "value_db": 55,
                                "assessed_value_db": 54, "check": "fails", "margin_db": -1,
                                "tolerance_db": 0}           # a single command: strict
    assert d["bands_hz"][0] == 100 and d["bands_hz"][-1] == 3150 and len(d["bands_hz"]) == 16
    assert np.allclose(d["bands"]["standardized_level_difference_DnT_db"], res.dnt, atol=0.006)
    assert np.allclose(d["bands"]["reverberation_time_s"], res.t, atol=0.0006)
    assert d["bands"]["reference_curve_shifted_db"][7] == 54            # rating at 500 Hz
    assert d["files"]["source"][0] == {"name": "luchtgeluid_bron_L2.SVL", "measured_at": "2026-09-22T12:11:34",
                                       "instrument": "SV 977D", "serial": 99942}
    assert set(d["files"]) == {"source", "receiver", "background", "rt"}
    assert str(S) not in out


@needs_samples
def test_impact_json_and_csv(capsys):
    code, out, _ = run(capsys, *imp_args("--format", "json", "--requirement", "58", "--basis", "wci"))
    d = strict_json(out)
    assert code == 0 and d["kind"] == "impact"
    assert (d["result"]["single_number_db"], d["result"]["CI"]) == (44, -1)
    assert "C" not in d["result"] and "Ctr" not in d["result"]
    assert d["requirement"]["compared_quantity"] == "L'nT,w + C_I"
    assert (d["requirement"]["assessed_value_db"], d["requirement"]["check"],
            d["requirement"]["margin_db"], d["requirement"]["direction"]) == (43, "complies", 15, "<=")
    code, out, _ = run(capsys, *imp_args("--format", "csv"))
    rows = list(csv.reader(io.StringIO(out)))
    assert rows[0][0] == "band_hz" and "standardized_impact_level_LnT_db" in rows[0]
    assert len(rows) == 17 and rows[1][0] == "100" and rows[-1][0] == "3150"


@needs_samples
def test_missing_values_are_null_not_nan(capsys):
    code, out, _ = run(capsys, *air_args("--format", "json", "--rt-kind", "edt"))
    d = strict_json(out)                                                 # would raise on NaN
    assert code == 0 and d["result"]["single_number_db"] is None and d["result"]["C"] is None
    assert d["bands"]["reverberation_time_s"][0] is None                  # EDT missing at 100 Hz
    assert d["bands"]["standardized_level_difference_DnT_db"][0] is None
    assert d["bands"]["reference_curve_shifted_db"] is None
    code, text, _ = run(capsys, *air_args("--rt-kind", "edt", "--requirement", "50"))
    assert "Rating not possible" in text and "no result" in text.lower()


@needs_samples
def test_strict_exit_status(capsys):
    assert run(capsys, *air_args("--requirement", "54", "--strict"))[0] == 0     # complies
    assert run(capsys, *air_args("--requirement", "55", "--strict"))[0] == 1     # fails
    assert run(capsys, *air_args("--requirement", "55"))[0] == 0                 # without --strict
    assert run(capsys, *imp_args("--requirement", "40", "--strict"))[0] == 1
    assert run(capsys, *imp_args("--requirement", "44", "--strict"))[0] == 0
    assert run(capsys, *air_args("--strict"))[0] == 0                            # no requirement


@needs_samples
def test_several_files_are_averaged(capsys):
    args = ["airborne", "--source", S / "luchtgeluid_bron_L2.SVL", "--receiver", S / "luchtgeluid_ontvangst_L2.SVL", S / "luchtgeluid_ontvangst_L2.SVL",
            "--background", S / "ontvangstruimte_BG_L20.SVL", "--rt", S / "ontvangstruimte_RT_L11.SVL", S / "ontvangstruimte_RT_L11.SVL",
            "--format", "json"]
    d = strict_json(run(capsys, *args)[1])
    assert d["result"]["single_number_db"] == 54                         # identical files: same
    assert len(d["files"]["receiver"]) == 2 and "averaged over several files" in d["remarks"]


@needs_samples
def test_output_file(capsys, tmp_path):
    target = tmp_path / "r.json"
    code, out, err = run(capsys, *air_args("--format", "json", "--output", target))
    assert code == 0 and out == "" and "written" in err
    assert strict_json(target.read_text(encoding="utf-8"))["kind"] == "airborne"


# ------------------------------------------------------------------ errors
@needs_samples
def test_errors_exit_2_with_a_message(capsys):
    code, out, err = run(capsys, "airborne", "--source", S / "nope.SVL", "--receiver", S / "luchtgeluid_ontvangst_L2.SVL",
                         "--background", S / "ontvangstruimte_BG_L20.SVL", "--rt", S / "ontvangstruimte_RT_L11.SVL")
    assert code == 2 and out == "" and err.startswith("error: file not found")
    code, out, err = run(capsys, *imp_args("--rt", S / "contactgeluid_L4.SVL"))        # a level file as RT file
    assert code == 2 and "reverberation time" in err
    code, _, err = run(capsys, "info", S / "README.md")
    assert code == 2 and "not a readable level or reverberation time file" in err
    assert err.count("bad magic") == 1                                      # the reason only once
    code, _, err = run(capsys, "building", S / "missing.json")
    assert code == 2 and "project file not found" in err


def test_usage_errors_are_argparse_exits(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["airborne", "--source", "a.SVL"])                         # required options missing
    assert e.value.code == 2
    with pytest.raises(SystemExit):
        cli.main([])
    capsys.readouterr()


def test_broken_pipe_is_quiet(monkeypatch, capsys):
    def boom(text, args):
        raise BrokenPipeError
    monkeypatch.setattr(cli, "_emit", boom)
    if not (S / "luchtgeluid_bron_L2.SVL").exists():
        pytest.skip("samples missing")
    assert cli.main([str(a) for a in air_args()]) == 0


# ------------------------------------------------------------------ info
@needs_samples
def test_info_level_and_reverberation_files(capsys):
    d = strict_json(run(capsys, "info", S / "luchtgeluid_bron_L2.SVL", "--format", "json")[1])
    assert (d["kind"], d["instrument"], d["serial"], d["duration_s"]) == ("level", "SV 977D", 99942, 10)
    assert d["measured_at"] == "2026-09-22T12:11:34" and d["laeq_db"] == pytest.approx(96.26)
    assert list(d["lzeq_db_by_band_hz"])[:2] == ["100", "125"] and len(d["lzeq_db_by_band_hz"]) == 16
    d = strict_json(run(capsys, "info", S / "ontvangstruimte_RT_L11.SVL", "--format", "json")[1])
    assert (d["kind"], d["records"]) == ("reverberation", 647)
    assert d["t30_s_by_band_hz"]["500"] == pytest.approx(1.312)
    both = strict_json(run(capsys, "info", S / "luchtgeluid_bron_L2.SVL", S / "ontvangstruimte_RT_L11.SVL", "--format", "json")[1])
    assert isinstance(both, list) and [x["kind"] for x in both] == ["level", "reverberation"]
    text = run(capsys, "info", S / "luchtgeluid_bron_L2.SVL")[1]
    assert text.startswith("luchtgeluid_bron_L2.SVL: level file, SV 977D #99942, measured 2026-09-22T12:11:34")


@pytest.mark.skipif(not (S / "977C_L1.SVL").exists() and not (S / "977C_RT_L34.SVL").exists(),
                    reason="977C samples missing")
def test_info_for_the_977c(capsys):
    if (S / "977C_L1.SVL").exists():
        d = strict_json(run(capsys, "info", S / "977C_L1.SVL", "--format", "json")[1])
        assert d["instrument"] == "SV 977C" and d["serial"] == 98053
    if (S / "977C_RT_L34.SVL").exists():
        d = strict_json(run(capsys, "info", S / "977C_RT_L34.SVL", "--format", "json")[1])
        assert d["kind"] == "reverberation" and d["records"] == 380


# ------------------------------------------------------------------ building
def building(tmp_path, with_error=False, requirements=(54, 40)):
    f = lambda n: str(S / n)                                              # noqa: E731
    p = Project(name="CLI building", background_files=[f("ontvangstruimte_BG_L20.SVL")])
    p.rooms = [Room("A"), Room("B", [f("ontvangstruimte_RT_L11.SVL")])]
    p.airborne = [AirborneSituation("A", "B", [f("luchtgeluid_bron_L2.SVL")], [f("luchtgeluid_ontvangst_L2.SVL")], "wall", requirements[0])]
    p.impact = [ImpactSituation("B", [f("contactgeluid_L4.SVL")], "A", "carpet", requirements[1])]
    if with_error:
        p.airborne.append(AirborneSituation("A", "B", [f("luchtgeluid_bron_L2.SVL")], [str(S / "gone.SVL")], "broken"))
    path = tmp_path / "b.json"
    save_project(p, path)
    return path


@needs_samples
def test_building_json_summary_and_measurements(capsys, tmp_path):
    code, out, _ = run(capsys, "building", building(tmp_path), "--format", "json")
    d = strict_json(out)
    assert code == 0 and d["project"] == "CLI building" and d["schema_version"] == 1
    assert d["summary"] == {"complies": 1, "tolerance": 0, "fails": 1, "inconclusive": 0,
                            "no_result": 0,
                            "none": 0, "errors": 0}
    names = [m["name"] for m in d["measurements"]]
    assert names == ["airborne A to B (wall)", "impact A to B (carpet)"]
    a, i = d["measurements"]
    assert a["result"]["single_number_db"] == 54 and a["requirement"]["check"] == "complies"
    assert i["result"]["CI"] == -1 and i["requirement"]["check"] == "fails"
    assert i["requirement"]["margin_db"] == -4                             # 44 against at most 40
    assert d["equipment"] == [{"instrument": "SV 977D", "serial": 99942, "used_for": ["source"]},
                              {"instrument": "SV 977D", "serial": 156226,
                               "used_for": ["receiver", "tapping", "background", "rt"]}]


@needs_samples
def test_building_text_csv_and_strict(capsys, tmp_path):
    path = building(tmp_path)
    code, out, _ = run(capsys, "building", path, "--strict")
    assert code == 1                                                       # the impact one fails
    assert "1 comply, 1 do not comply" in out and "airborne A to B (wall)" in out
    code, out, _ = run(capsys, "building", path, "--format", "csv")
    rows = list(csv.DictReader(io.StringIO(out)))
    assert [r["name"] for r in rows] == ["airborne A to B (wall)", "impact A to B (carpet)"]
    assert rows[0]["single_number_db"] == "54" and rows[0]["check"] == "complies"
    assert rows[1]["C_or_CI"] == "-1" and rows[1]["Ctr"] == "" and rows[1]["margin_db"] == "-4"
    ok = building(tmp_path, requirements=(54, 58))
    assert run(capsys, "building", ok, "--strict")[0] == 0


@needs_samples
def test_building_error_measurement_does_not_stop_the_others(capsys, tmp_path):
    path = building(tmp_path, with_error=True)
    code, out, _ = run(capsys, "building", path, "--format", "json")
    d = strict_json(out)
    broken = next(m for m in d["measurements"] if m["comment"] == "broken")
    assert code == 0 and broken["ok"] is False and "file not found: gone.SVL" in broken["error"]
    assert broken["result"] is None and d["summary"]["errors"] == 1
    assert sum(1 for m in d["measurements"] if m["ok"]) == 2
    assert run(capsys, "building", path, "--strict")[0] == 1               # an error counts as a failure
    assert "ERROR: file not found: gone.SVL" in run(capsys, "building", path)[1]


@needs_samples
def test_building_pdf_options(capsys, tmp_path):
    pypdf = pytest.importorskip("pypdf")
    path = building(tmp_path)
    out = tmp_path / "r.pdf"
    code, _, err = run(capsys, "building", path, "--pdf", out, "--date", "2026-10-01",
                       "--measurement-files")                  # off by default, switched on
    assert code == 0 and "report written" in err and out.read_bytes()[:5] == b"%PDF-"
    pages = [" ".join(p.extract_text().split()) for p in pypdf.PdfReader(str(out)).pages]
    assert "1 oktober 2026" in pages[0] and len(pages) == 6
    assert "luchtgeluid_bron_L2.SVL (22/09/2026 12:11)" in " ".join(pages)
    plain = tmp_path / "p.pdf"
    run(capsys, "building", path, "--pdf", plain, "--date", "2026-10-01")
    text = " ".join(p.extract_text() for p in pypdf.PdfReader(str(plain)).pages)
    assert "luchtgeluid_bron_L2.SVL" not in text and "Meetbestanden" not in text
    short = tmp_path / "s.pdf"
    run(capsys, "building", path, "--pdf", short, "--no-dates", "--no-measurement-pages",
        "--no-band-tables", "--no-photos")
    pages = [" ".join(p.extract_text().split()) for p in pypdf.PdfReader(str(short)).pages]
    assert len(pages) == 4 and "22/09/2026" not in " ".join(pages)
    code, _, err = run(capsys, "building", path, "--pdf", tmp_path / "no_folder" / "x.pdf")
    assert code == 2 and "could not write" in err


@needs_samples
def test_building_pdf_switches(capsys, tmp_path):
    pypdf = pytest.importorskip("pypdf")
    from calc.building import load_project, save_project
    path = building(tmp_path)

    def text(pdf):
        return " ".join(" ".join(p.extract_text().split()) for p in pypdf.PdfReader(str(pdf)).pages)

    full = tmp_path / "full.pdf"
    run(capsys, "building", path, "--pdf", full)
    assert "Apparatuur" in text(full) and "Toelichting" in text(full) and "Voldoet" in text(full)
    out = tmp_path / "a.pdf"
    run(capsys, "building", path, "--pdf", out, "--no-summary", "--no-equipment", "--no-notes",
        "--no-requirements")
    got = text(out)
    assert "Apparatuur" not in got and "Toelichting" not in got and "Voldoet" not in got
    assert "Eisen:" not in got and "Geluidsmetingen" in got
    # the choices saved in the project (made in the viewer) are the starting point of the command line
    project = load_project(path)
    project.report_options = {"equipment": False, "notes": False}
    saved = tmp_path / "saved.json"
    save_project(project, saved)
    out2 = tmp_path / "b.pdf"
    run(capsys, "building", saved, "--pdf", out2)
    got2 = text(out2)
    assert "Apparatuur" not in got2 and "Toelichting" not in got2 and "Voldoet" in got2


# ------------------------------------------------------------------ documentation stays in sync
def test_example_json_is_regenerated_from_the_fabricated_measurement():
    text = (ROOT / "docs" / "example-airborne.json").read_text(encoding="utf-8")
    expected = json.dumps(evaluated_to_dict(example_airborne()), indent=2, ensure_ascii=False,
                          allow_nan=False) + "\n"
    assert text == expected, "regenerate docs/example-airborne.json (see AGENTS.md)"
    d = strict_json(text)
    assert d["result"]["single_number_db"] == 55 and d["requirement"]["check"] == "complies"


def test_every_json_key_is_documented():
    doc = (ROOT / "docs" / "cli.md").read_text(encoding="utf-8")
    d = evaluated_to_dict(example_airborne())
    keys = set(d) | set(d["result"]) | set(d["requirement"]) | set(d["bands"])
    keys -= {"source_room"}                                    # documented as the pair below
    missing = [k for k in sorted(keys) if f"`{k}" not in doc and f".{k}" not in doc]
    assert not missing, f"undocumented keys in docs/cli.md: {missing}"
    for k in ("source_room", "tapping_room", "CI", "bands.*", "unfavourable_deviation_limit_db"):
        assert k in doc


def test_examples_are_fabricated_and_free_of_folders():
    text = (ROOT / "docs" / "example-airborne.json").read_text(encoding="utf-8")
    assert "/" not in text.replace("n/a", "") and "\\" not in text
    assert "room A" in text and "100001" in text                  # made-up serial numbers


@needs_samples
def test_python_m_calc_runs_as_a_program():
    r = subprocess.run([sys.executable, "-m", "calc", "info", str(S / "luchtgeluid_bron_L2.SVL")], cwd=ROOT,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "level file, SV 977D #99942" in r.stdout
    r = subprocess.run([sys.executable, "-m", "calc", "--help"], cwd=ROOT, capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0 and "airborne" in r.stdout and "building" in r.stdout
