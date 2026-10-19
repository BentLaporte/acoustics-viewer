"""Measurement uncertainty per ISO 12999-1:2020 (situation B, k = 1)."""
import dataclasses
import datetime as dt
from pathlib import Path

import pytest

from calc.examples import example_airborne
from calc.iso12999 import COVERAGE_K, expanded_uncertainty
from calc.results import evaluated_to_dict

PM = chr(0xb1)                                         # plus-minus sign


def test_values_of_table_3_and_table_5_situation_b():
    assert COVERAGE_K == 1.0
    assert expanded_uncertainty("airborne", "w") == 0.9      # DnT,w
    assert expanded_uncertainty("airborne", "wc") == 0.9     # DnT,w + C
    assert expanded_uncertainty("airborne", "wctr") == 1.1   # DnT,w + Ctr
    assert expanded_uncertainty("impact", "w") == 1.0        # L'nT,w
    assert expanded_uncertainty("impact", "wci") == 1.0      # L'nT,w + CI
    assert expanded_uncertainty("airborne", "w", k=1.65) == 1.5      # U = k u, to 0,1 dB
    assert expanded_uncertainty("installation", "laeq") is None      # outside 12999-1


def test_evaluated_and_json_carry_the_uncertainty_of_the_compared_value():
    ev = example_airborne()
    assert ev.uncertainty == 0.9
    ctr = dataclasses.replace(ev, basis="wctr")
    assert ctr.uncertainty == 1.1
    out = evaluated_to_dict(ctr)["uncertainty"]
    assert out == {"compared_quantity": "DnT,w + Ctr", "expanded_db": 1.1,
                   "coverage_factor": 1.0, "situation": "B"}
    assert dataclasses.replace(ev, result=None).uncertainty is None


pypdf = pytest.importorskip("pypdf")
S = Path(__file__).parent.parent / "samples"
NEED = ["luchtgeluid_bron_L2.SVL", "luchtgeluid_ontvangst_L2.SVL", "ontvangstruimte_BG_L20.SVL",
        "ontvangstruimte_RT_L11.SVL"]


@pytest.mark.skipif(not all((S / n).exists() for n in NEED), reason="sample files missing")
def test_report_shows_the_uncertainty_and_the_switch_removes_it(tmp_path):
    pytest.importorskip("reportlab")
    from calc.building import AirborneSituation, Project, Room, evaluate_project
    from export.pdf_report import ReportOptions, build_pdf_report
    p = Project(name="U", background_files=[str(S / "ontvangstruimte_BG_L20.SVL")])
    p.rooms = [Room("A"), Room("B", [str(S / "ontvangstruimte_RT_L11.SVL")])]
    p.airborne = [AirborneSituation("A", "B", [str(S / "luchtgeluid_bron_L2.SVL")],
                                    [str(S / "luchtgeluid_ontvangst_L2.SVL")], requirement=54)]

    def text(**opts):
        out = build_pdf_report(p, evaluate_project(p), tmp_path / f"r{len(opts)}.pdf",
                               ReportOptions(date=dt.date(2026, 10, 1), **opts))
        return " ".join(" ".join(pg.extract_text().split())
                        for pg in pypdf.PdfReader(str(out)).pages)

    on, off = text(), text(uncertainty=False)
    assert f"DnT,w = 54 {PM} 0,9 dB (k = 1; ISO 12999-1:2020, situatie B)" in on
    assert "de meetonzekerheid wordt daarbij niet apart verrekend" in on   # NBN tolerance
    assert "12999" not in off and PM not in off
