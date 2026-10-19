"""Report switch 'measurement_remarks': the remarks column and per-page remarks can go, what the
standards require stays (ISO 16283-1/-2 clause 14 limit values, ISO 10052 6.2.1)."""
import datetime as dt
from pathlib import Path

import pytest

pypdf = pytest.importorskip("pypdf")
pytest.importorskip("reportlab")
pytest.importorskip("matplotlib")

from calc.building import (AirborneSituation, InstallationSituation, Project, Room,  # noqa: E402
                           evaluate_project)
from calc.installation import Recording  # noqa: E402
from export import report_text as T  # noqa: E402
from export.pdf_report import ReportOptions, build_pdf_report  # noqa: E402

S = Path(__file__).parent.parent / "samples"
L22, BG_I = S / "installatiegeluid_L22.SVL", S / "installatiegeluid_BG_L39.SVL"
RT_I = [S / "installatiegeluid_RT_L15.SVL", S / "installatiegeluid_RT_L16.SVL"]
NEED = [S / n for n in ("luchtgeluid_bron_L2.SVL", "luchtgeluid_ontvangst_L2.SVL",
                        "ontvangstruimte_BG_L20.SVL", "ontvangstruimte_RT_L11.SVL")]
needs_samples = pytest.mark.skipif(not all(p.exists() for p in [*NEED, L22, BG_I, *RT_I]),
                                   reason="sample files missing")


def project(tmp_path) -> Project:
    from helpers import make_variant
    loud = make_variant(S / "ontvangstruimte_BG_L20.SVL", tmp_path / "loud.SVL", 22.0)
    quiet_install = make_variant(L22, tmp_path / "q.SVL", -8.0)     # within 6 dB of background
    p = Project(name="R", background_files=[str(S / "ontvangstruimte_BG_L20.SVL")])
    p.rooms = [Room("A"), Room("C", [str(S / "ontvangstruimte_RT_L11.SVL")], [str(loud)]),
               Room("Slaapkamer", [str(x) for x in RT_I], [str(BG_I)])]
    p.airborne = [AirborneSituation("A", "C", [str(S / "luchtgeluid_bron_L2.SVL")],
                                    [str(S / "luchtgeluid_ontvangst_L2.SVL")], "lawaai"),
                  AirborneSituation("A", "C", [str(S / "missing.SVL")],
                                    [str(S / "luchtgeluid_ontvangst_L2.SVL")], "kapot")]
    p.installation = [InstallationSituation("Slaapkamer", [Recording(quiet_install)], "",
                                            "pomp")]
    return p


def text(p, tmp_path, name, **options) -> str:
    out = build_pdf_report(p, evaluate_project(p), tmp_path / name,
                           ReportOptions(date=dt.date(2026, 10, 19), **options))
    return " ".join(" ".join(pg.extract_text().split()) for pg in pypdf.PdfReader(str(out)).pages)


@needs_samples
def test_remarks_off_keeps_what_the_standards_require(tmp_path):
    p = project(tmp_path)
    on = text(p, tmp_path, "on.pdf")
    assert T.COL_REMARKS in on and "binnen 6 dB" in on            # the column and its remarks
    off = text(p, tmp_path, "off.pdf", measurement_remarks=False)
    assert T.COL_REMARKS not in off and "band(en) binnen 6 dB" not in off
    assert T.LIMIT_PREFIX["airborne"] + "4" in off                # limit values in the band table
    assert T.DETAIL_INSTALL_OVER in off                           # ISO 10052 6.2.1 on its page
    assert "Zonder resultaat: luchtgeluid A naar C (kapot)" in off
    assert "Metingen met tertsbanden die slechts een grenswaarde" not in off   # shown elsewhere
    # no measurement pages and no band tables: the notes name the measurements
    bare = text(p, tmp_path, "bare.pdf", measurement_remarks=False,
                per_measurement_pages=False, per_band_tables=False)
    assert "slechts een grenswaarde zijn (6 dB of minder boven het " \
           "achtergrondgeluiddrukniveau): luchtgeluid A naar C (lawaai)" in bare
    assert "waarde overschat: installatiegeluid in Slaapkamer (pomp)" in bare
