"""PDF report of a building: results, compliance, comparison and one page per measurement.

The report is in Dutch; every fixed text comes from `report_text.py`. What it contains is set by
`ReportOptions` (see `report_options.py`: one switch per part of the content).

Built with reportlab (layout) and matplotlib (charts). The fonts are the DejaVu fonts that ship
with matplotlib, so characters like the arrow, >=, <= and the minus sign always work.
Nothing in here depends on the GUI.
"""
from __future__ import annotations

import datetime as dt
import io
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib
import numpy as np
from reportlab.lib import colors as rl
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, Image, KeepTogether,
                                PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle)

from calc.building import (AIRBORNE_BASES, IMPACT_BASES, INSTALLATION_QUANTITIES,
                           INTEGRATED_NOTE, Evaluated, Project, equipment_used, natural_key)
from calc.colors import style_of
from calc.installation import OCTAVE_THIRDS
from calc.iso717 import BANDS
from svl.parser import SvlError, read_svl

from . import charts
from . import report_text as T
from .photos import PreparedPhoto, prepare_photo
from .report_options import ReportOptions
from .report_text import date_text as _date_text
from .report_text import number as num

PAGE = A4
MARGIN_X, MARGIN_TOP, MARGIN_BOTTOM = 18 * mm, 16 * mm, 20 * mm
FRAME_W = PAGE[0] - 2 * MARGIN_X                       # 174 mm
FONT, FONT_B = "DejaVu", "DejaVu-Bold"
# 'tolerance' (complies only within the NBN tolerance) is a paler, more olive green than a clean pass
CHECK_BG = {"complies": "#d5f5e3", "tolerance": "#eef6d5", "fails": "#f5b7b1",
            "inconclusive": "#fdebd0", "no_result": "#eaecee", "none": None}
CHECK_FG = {"complies": "#1e8449", "tolerance": "#6b8e23", "fails": "#c0392b",
            "inconclusive": "#b9770e"}
LIMIT_BG = "#fdebd0"
HEAD_BG = "#2c3e50"
BARS_PER_CHART = 10
ROLE_TEXT = T.ROLE_TEXT

__all__ = ["ReportOptions", "build_pdf_report", "default_report_name", "when_text"]

_fonts_ready = False


def _register_fonts() -> None:
    global _fonts_ready
    if _fonts_ready:
        return
    folder = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    for name, file in (("DejaVu", "DejaVuSans.ttf"), ("DejaVu-Bold", "DejaVuSans-Bold.ttf"),
                       ("DejaVu-Oblique", "DejaVuSans-Oblique.ttf"),
                       ("DejaVu-BoldOblique", "DejaVuSans-BoldOblique.ttf")):
        pdfmetrics.registerFont(TTFont(name, str(folder / file)))
    pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold",
                                  italic="DejaVu-Oblique", boldItalic="DejaVu-BoldOblique")
    _fonts_ready = True


# ----------------------------------------------------------------------------- text helpers
_SUBSCRIPTS = [("LAFmax,nT", "L<sub>AFmax,nT</sub>"), ("LAeq,nT", "L<sub>Aeq,nT</sub>"),
               ("LAFmax", "L<sub>AFmax</sub>"), ("LAeq", "L<sub>Aeq</sub>"),
               ("DnT,w", "D<sub>nT,w</sub>"), ("L'nT,w", "L'<sub>nT,w</sub>"),
               ("DnT", "D<sub>nT</sub>"), ("L'nT", "L'<sub>nT</sub>"),
               ("C_I", "C<sub>I</sub>"), ("Ctr", "C<sub>tr</sub>")]


def mk(text: str) -> str:
    """Fixed texts of the report: escape XML and set the quantity symbols with subscripts."""
    text = escape(text)
    for plain, marked in _SUBSCRIPTS:
        text = text.replace(plain, marked)
    return text


def head_text(text: str) -> str:
    """Column header: fixed text with quantity symbols; '\n' = line break."""
    return mk(text).replace("\n", "<br/>")


def txt(text: str) -> str:
    """User text (names, remarks): escape only."""
    return escape(text)


def minus(v) -> str:
    return f"{int(v):d}".replace("-", "\u2212")


def styles() -> dict:
    _register_fonts()

    def s(name, **kw):
        kw.setdefault("fontName", FONT)
        kw.setdefault("textColor", rl.HexColor("#1b2631"))
        return ParagraphStyle(name, **kw)

    return {
        "title": s("title", fontName=FONT_B, fontSize=20, leading=24, spaceAfter=2),
        "subtitle": s("subtitle", fontSize=12.5, leading=16, textColor=rl.HexColor("#566573")),
        "h1": s("h1", fontName=FONT_B, fontSize=12.5, leading=16, spaceBefore=10, spaceAfter=5),
        "h2": s("h2", fontName=FONT_B, fontSize=10, leading=13, spaceBefore=6, spaceAfter=3),
        "body": s("body", fontSize=8.5, leading=11.5),
        "small": s("small", fontSize=7.3, leading=9.6, textColor=rl.HexColor("#424949")),
        "cell": s("cell", fontSize=7.6, leading=9.6),
        "cellc": s("cellc", fontSize=7.6, leading=9.6, alignment=1),
        "cellbox": s("cellbox", fontSize=7.6, leading=9.6, alignment=1, spaceAfter=3),
        "cellb": s("cellb", fontName=FONT_B, fontSize=8, leading=10, alignment=1),
        "tiny": s("tiny", fontSize=6.4, leading=8),
        "tinyc": s("tinyc", fontSize=6.4, leading=8, alignment=1),
        "head": s("head", fontName=FONT_B, fontSize=7.4, leading=9, alignment=1,
                  textColor=rl.white),
        "colhead": s("colhead", fontName=FONT_B, fontSize=6.7, leading=8.2, alignment=1,
                     textColor=rl.white),
        "tinyhead": s("tinyhead", fontName=FONT_B, fontSize=6.3, leading=7.6, alignment=1,
                      textColor=rl.white),
        "big": s("big", fontName=FONT_B, fontSize=13, leading=20, spaceAfter=3),
    }


def _table(rows, widths_mm, st: dict, repeat: int = 1, extra=()) -> Table:
    t = Table(rows, colWidths=[w * mm for w in widths_mm], repeatRows=repeat)
    style = [("BACKGROUND", (0, 0), (-1, repeat - 1), rl.HexColor(HEAD_BG)),
             ("GRID", (0, 0), (-1, -1), 0.3, rl.HexColor("#b2babb")),
             ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
             ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
    style += list(extra)
    t.setStyle(TableStyle(style))
    return t


def _image(png: bytes, width=FRAME_W) -> Image:
    w, h = ImageReader(io.BytesIO(png)).getSize()
    return Image(io.BytesIO(png), width=width, height=width * h / w)


def _band_image(png: bytes) -> Image:
    """A chart of values per band at its own size (pixels / DPI), never stretched: its scale on
    paper is then 5 mm per one-third octave and 20 mm per 10 dB (ISO 16283 clause 12)."""
    w, h = ImageReader(io.BytesIO(png)).getSize()
    return Image(io.BytesIO(png), width=w / charts.DPI * 72, height=h / charts.DPI * 72)


# ----------------------------------------------------------------------------- options
def default_report_name(project: Project) -> str:
    safe = "".join(c for c in project.name if c not in '\\/:*?"<>|').strip() or "Building"
    return f"{safe} - rapport.pdf"


# the requirement bases that use an adaptation term: that term is then part of the checked value
_BASIS_TERM = {"wc": "c", "wctr": "ctr", "wci": "ci"}


def shown_terms(options: ReportOptions, project: Project, evs: list, kind: str) -> set:
    """Which adaptation terms ('c', 'ctr' for airborne, 'ci' for impact) the report shows.

    A term that a requirement is checked against (basis DnT,w + C, ...) is always shown while
    requirements are in the report: the check would otherwise rest on a number the reader
    cannot see."""
    wanted = {"c": options.term_c, "ctr": options.term_ctr, "ci": options.term_ci}
    allowed = {"c", "ctr"} if kind == "airborne" else {"ci"}
    terms = {t for t in allowed if wanted[t]}
    if options.requirements and any(e.requirement is not None for e in evs if e.kind == kind):
        basis = project.airborne_basis if kind == "airborne" else project.impact_basis
        if _BASIS_TERM.get(basis) in allowed:
            terms.add(_BASIS_TERM[basis])
    return terms


def limit_text(value, is_limit: bool, kind: str) -> str:
    """A band value; a limit value (band close to the background) as 'DnT >= 45,3' would read:
    '\u226545,3' (airborne) or '\u226445,3' (impact), as ISO 16283-1/-2 clause 14 i) asks."""
    shown = num(value)
    return f"{T.LIMIT_PREFIX[kind]}{shown}" if is_limit and shown != "-" else shown


def notes_shown(ev: Evaluated, options: ReportOptions) -> list[str]:
    """The remarks of a measurement as the report shows them (English, see T.note_text): the
    'integrated method' remark of installation noise has its own switch."""
    if options.integrated_method_note:
        return list(ev.notes)
    return [n for n in ev.notes if n != INTEGRATED_NOTE]


# ----------------------------------------------------------------------------- page furniture
def _canvas_maker(left: str, right: str):
    class NumberedCanvas(canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved = []

        def showPage(self):
            self._saved.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved)
            for state in self._saved:
                self.__dict__.update(state)
                self._footer(total)
                super().showPage()
            super().save()

        def _footer(self, total):
            y = 11 * mm
            self.setStrokeColor(rl.HexColor("#b2babb"))
            self.setLineWidth(0.4)
            self.line(MARGIN_X, y + 4 * mm, PAGE[0] - MARGIN_X, y + 4 * mm)
            self.setFont(FONT, FOOTER_SIZE)
            self.setFillColor(rl.HexColor("#566573"))
            # page number and date share the right side, so a long project name (left) never
            # runs into them; the name gets the rest of the width, on at most two lines
            page_date = f"{T.PAGE_OF.format(page=self._pageNumber, total=total)}   |   {right}"
            self.drawRightString(PAGE[0] - MARGIN_X, y, page_date)
            room = FRAME_W - pdfmetrics.stringWidth(page_date, FONT, FOOTER_SIZE) - 8 * mm
            for i, line in enumerate(footer_lines(left, room)):
                self.drawString(MARGIN_X, y - i * 3 * mm, line)

    return NumberedCanvas


FOOTER_SIZE = 7.2


def footer_lines(text: str, width: float, max_lines: int = 2) -> list[str]:
    """The project name for the footer: wrapped to the width (points), at most max_lines lines;
    only a name that still does not fit ends in an ellipsis."""
    lines = simpleSplit(text, FONT, FOOTER_SIZE, width) or [""]
    if len(lines) <= max_lines:
        return lines
    last = " ".join(lines[max_lines - 1:])
    while last and pdfmetrics.stringWidth(last + "\u2026", FONT, FOOTER_SIZE) > width:
        last = last[:-1]
    return lines[:max_lines - 1] + [last.rstrip() + "\u2026"]


# ----------------------------------------------------------------------------- content blocks
def _check_cell(ev: Evaluated, st: dict):
    c = ev.check
    if c.status == "none":
        return Paragraph("", st["cellc"]), None
    margin = "" if c.margin is None else \
        f"<br/>({c.margin:+d} dB)".replace("-", "\u2212")      # result on line 1, margin on line 2
    fg = CHECK_FG.get(c.status, "#424949")
    return Paragraph(f"<font color='{fg}'><b>{T.CHECK_TEXT[c.status]}{margin}</b></font>",
                     st["cellc"]), CHECK_BG[c.status]


def _requirement_text(ev: Evaluated) -> str:
    if ev.requirement is None:
        return ""
    sign = "\u2265" if ev.kind == "airborne" else "\u2264"
    return f"{sign} {ev.requirement} dB"


def _overview_table(evs: list, kind: str, project: Project, options: ReportOptions,
                    st: dict) -> Table:
    """The results table of one kind. Columns follow the options: the adaptation terms that are
    switched off and the requirement and check columns (requirements off) are left out."""
    airborne = kind == "airborne"
    installation = kind == "installation"
    terms = shown_terms(options, project, evs, kind) if not installation else set()
    # (key, header, width in mm; None = shares what is left, name 55 % and remarks 45 %)
    if installation:            # one value; LAeq,nT or LAFmax,nT is chosen per measurement
        cols = [("name", T.COL_MEASUREMENT_IMPACT, None), ("value", T.COL_VALUE, 14),
                ("quantity", T.COL_QUANTITY, 19)]
    else:
        cols = [("name", T.COL_MEASUREMENT if airborne else T.COL_MEASUREMENT_IMPACT, None),
                ("value", "DnT,w" if airborne else "L'nT,w", 13)]
    if airborne:
        cols += [("c", "C", 8)] if "c" in terms else []
        cols += [("ctr", "Ctr", 9)] if "ctr" in terms else []
    elif "ci" in terms:
        cols += [("ci", "C_I", 8)]
    if options.requirements:
        if installation:
            req_head = T.COL_REQUIREMENT_PLAIN
        else:
            basis = (AIRBORNE_BASES[project.airborne_basis] if airborne
                     else IMPACT_BASES[project.impact_basis])
            req_head = T.COL_REQUIREMENT.format(basis=basis)
        cols += [("req", req_head, 18 if installation else 26 if airborne else 24),
                 ("check", T.COL_CHECK, 30)]
    if options.measurement_remarks:
        cols += [("remarks", T.COL_REMARKS, None)]
    left = FRAME_W / mm - sum(w for *_, w in cols if w)
    share = {"name": 0.55, "remarks": 0.45} if options.measurement_remarks else {"name": 1.0}
    widths = [w if w else left * share[key] for key, _, w in cols]

    rows = [[Paragraph(mk(h), st["head"]) for _, h, _ in cols]]
    extra = []
    for i, ev in enumerate(evs, start=1):
        r = ev.result
        cells, bg = {}, None
        cells["name"] = Paragraph(txt(ev.label), st["cell"])
        cells["value"] = Paragraph(f"<b>{ev.value if ev.value is not None else '-'}</b>",
                                   st["cellb"])
        for key, term in (("c", "c"), ("ctr", "ctr"), ("ci", "ci")):
            value = getattr(r, term, None) if r else None
            cells[key] = Paragraph(minus(value) if value is not None else "-", st["cellc"])
        cells["quantity"] = Paragraph(mk(ev.basis_label), st["cellc"])
        cells["req"] = Paragraph(_requirement_text(ev), st["cellc"])
        cells["check"], bg = _check_cell(ev, st)
        cells["remarks"] = Paragraph(
            txt("; ".join(T.note_text(n) for n in notes_shown(ev, options))), st["small"])
        rows.append([cells[key] for key, _, _ in cols])
        if options.requirements and bg:
            j = [key for key, _, _ in cols].index("check")
            extra.append(("BACKGROUND", (j, i), (j, i), rl.HexColor(bg)))
        if not ev.ok:
            extra.append(("BACKGROUND", (0, i), (0, i), rl.HexColor("#fadbd8")))
    return _table(rows, widths, st, extra=extra)


def _counts(evs) -> dict:
    c = {"complies": 0, "tolerance": 0, "fails": 0, "inconclusive": 0, "no_result": 0, "none": 0}
    for e in evs:
        c[e.check.status] += 1
    return c


def measurement_dates_text(evs: list) -> str:
    """The days on which the files of the included measurements were recorded (ISO 16283
    clause 14 d): one to three days are listed, more as a period. '' if no file has a date."""
    days = sorted({i.measured_at.date() for e in evs if e.ok and e.result.info
                   for infos in e.result.info.values() for i in infos if i.measured_at})
    if not days:
        return ""
    if len(days) <= 3:
        return ", ".join(_date_text(d) for d in days)
    return f"{_date_text(days[0])} {T.PERIOD_TO} {_date_text(days[-1])}"


def method_lines(evs: list, options: ReportOptions) -> list[str]:
    """One line per kind of measurement in the report: the standards that were followed.

    Installation noise measured with the integrated method deviates from ISO 10052 6.3.4: the
    line names the deviation, or, when the 'integrated method' remark is switched off, it does
    not claim ISO 10052 as the measurement method (only its formulas)."""
    kinds = [k for k in ("airborne", "impact", "installation") if any(e.kind == k for e in evs)]
    lines = []
    for kind in kinds:
        if kind != "installation":
            lines.append(T.METHOD[kind])
            continue
        integrated = any(e.ok and e.result.method == "integrated"
                         for e in evs if e.kind == "installation")
        if not integrated:
            lines.append(T.METHOD[kind])
        elif options.integrated_method_note:
            lines.append(T.METHOD[kind] + T.METHOD_INSTALLATION_DEVIATION)
        else:
            lines.append(T.METHOD_INSTALLATION_FORMULAS)
    return lines


def _title_block(project: Project, evs: list, date: dt.date, options: ReportOptions,
                 st: dict) -> list:
    info = project.report
    story = [Paragraph(T.TITLE, st["title"]),
             Paragraph(txt(project.name), st["subtitle"]), Spacer(1, 5 * mm)]
    facts = []
    if info.client:
        facts.append((T.FACT_CLIENT, txt(info.client)))
    if info.location:
        facts.append((T.FACT_LOCATION, txt(info.location)))
    if info.author:
        facts.append((T.FACT_AUTHOR, txt(info.author)))
    facts.append((T.FACT_DATE, _date_text(date)))
    tested = measurement_dates_text(evs)
    if tested:                     # the date of the test is required, whatever the switches say
        facts.append((T.FACT_TEST_DATE, tested))
    methods = method_lines(evs, options)
    if methods:
        facts.append((T.FACT_METHOD, "<br/>".join(mk(m[0].upper() + m[1:]) for m in methods)))
    kinds = {e.kind for e in evs}
    # airborne and impact use the project's choice; installation noise always T30 (else T20)
    rt = [T.RT_TEXT[project.rt_kind]] if kinds & {"airborne", "impact"} or not kinds else []
    rt += [T.RT_INSTALLATION] if "installation" in kinds else []
    facts.append((T.FACT_RT, "; ".join(rt)))
    basis = []
    if "airborne" in kinds:
        basis.append(f"{T.KIND_WORD['airborne']}: {AIRBORNE_BASES[project.airborne_basis]}")
    if "impact" in kinds:
        basis.append(f"{T.KIND_WORD['impact']}: {IMPACT_BASES[project.impact_basis]}")
    quantities = sorted({e.basis_label for e in evs if e.kind == "installation"})
    if quantities:
        basis.append(f"{T.KIND_WORD['installation']}: {' / '.join(quantities)}")
    if options.requirements and any(e.requirement is not None for e in evs) and basis:
        facts.append((T.FACT_BASIS, mk("; ".join(basis))))
    rows = [[Paragraph(f"<b>{k}</b>", st["body"]), Paragraph(v, st["body"])] for k, v in facts]
    t = Table(rows, colWidths=[52 * mm, FRAME_W - 52 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LINEBELOW", (0, 0), (-1, -1), 0.3, rl.HexColor("#d5d8dc")),
                           ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(t)
    if options.remarks and info.remarks.strip():
        story += [Spacer(1, 4 * mm), Paragraph(f"<b>{T.REMARKS}</b>", st["body"])]
        story += [Paragraph(txt(line), st["body"]) for line in info.remarks.strip().splitlines()
                  if line.strip()]
    return story


def _summary(evs: list, options: ReportOptions, st: dict) -> list:
    counts = {k: sum(1 for e in evs if e.kind == k) for k in T.KIND_WORD}
    parts = [f"{n} {T.KIND_WORD[k]}" for k, n in counts.items() if n]
    text = f"<b>{T.count_metingen(len(evs))}</b> ({', '.join(parts)}). "
    if options.requirements:
        c = _counts(evs)
        if len(evs) - c["none"]:
            def verb(n, one, many):
                return one if n == 1 else many

            passed = c["complies"] + c["tolerance"]
            within = f" (waarvan {c['tolerance']} binnen de tolerantie)" if c["tolerance"] else ""
            bits = [f"<font color='{CHECK_FG['complies']}'><b>{passed} "
                    f"{verb(passed, 'voldoet', 'voldoen')}</b></font>{within}",
                    f"<font color='{CHECK_FG['fails']}'><b>{c['fails']} "
                    f"{verb(c['fails'], 'voldoet niet', 'voldoen niet')}</b></font>"]
            if c["inconclusive"]:
                bits.append(f"<font color='{CHECK_FG['inconclusive']}'><b>{c['inconclusive']} "
                            "niet conclusief</b></font>")
            if c["no_result"]:
                bits.append(f"{c['no_result']} zonder resultaat")
            if c["none"]:
                bits.append(f"{c['none']} zonder eis")
            text += "Eisen: " + ", ".join(bits) + "."
        else:
            text += "Er zijn geen eisen ingesteld."
    return [Spacer(1, 5 * mm), Paragraph(text, st["body"])]


def _term_sentence(names: list) -> str:
    if not names:
        return ""
    if len(names) == 1:
        return f"{names[0]} is een spectrumaanpassingsterm. "
    return f"{' en '.join(names)} zijn spectrumaanpassingstermen. "


def _notes(evs: list, project: Project, options: ReportOptions, st: dict) -> list:
    """The 'Toelichting': only the notes that belong to what the report shows."""
    all_evs = list(evs)
    kinds = {e.kind for e in evs}
    items = []
    if "airborne" in kinds:
        names = [n for k, n in (("c", "C"), ("ctr", "Ctr"))
                 if k in shown_terms(options, project, evs, "airborne")]
        items.append(mk("DnT,w is het gewogen gestandaardiseerde geluidsniveauverschil tussen "
                        "twee ruimten (hoger is beter). " + _term_sentence(names) +
                        "De beoordeling gebeurt op basis van de tertsbandniveaus van 100 tot "
                        "3150 Hz volgens ISO 717-1."))
    if "impact" in kinds:
        ci = "ci" in shown_terms(options, project, evs, "impact")
        items.append(mk("L'nT,w is het gewogen gestandaardiseerde contactgeluidsdrukniveau "
                        "(lager is beter). " +
                        ("C_I is de spectrumaanpassingsterm (100 tot 2500 Hz). " if ci else "") +
                        "De beoordeling gebeurt volgens ISO 717-2."))
    installation = [e for e in evs if e.kind == "installation"]
    if installation:
        items.append(mk(T.NOTE_INSTALLATION))
        if options.integrated_method_note and any(e.ok and e.result.method == "integrated"
                                                  for e in installation):
            items.append(T.NOTE_INTEGRATED)
    evs = [e for e in evs if e.kind != "installation"]      # the notes below: insulation only
    checked = [e for e in evs + installation if e.requirement is not None]
    nbn = any(e.tolerance for e in checked)
    if options.requirements and nbn:
        items.append(mk(T.NOTE_TOLERANCE))
    if options.uncertainty and any(e.uncertainty is not None for e in evs):
        items.append(T.NOTE_UNCERTAINTY)
        if options.requirements and checked:
            items.append(T.NOTE_UNCERTAINTY_CHECK_NBN if nbn else T.NOTE_UNCERTAINTY_CHECK)
    limit = [e for e in evs if e.ok and e.result.n_limit]
    if options.requirements:
        if any(e.requirement is not None for e in evs):
            items.append("Luchtgeluidresultaten moeten minstens gelijk zijn aan de eis en "
                         "contactgeluidresultaten hoogstens gelijk aan de eis. De marge is het "
                         "verschil in dB (positief = beter dan de eis).")
        if any(e.requirement is not None for e in installation):
            items.append(T.NOTE_INSTALL_REQUIREMENT)
        if any(e.check.status == "inconclusive" for e in installation):
            items.append(T.NOTE_INSTALL_INCONCLUSIVE)
        if any(e.check.status == "inconclusive" for e in evs):
            items.append("Niet conclusief: een of meer tersbanden liggen dicht bij het "
                         "achtergrondgeluiddrukniveau (6 dB of minder erboven). Zo'n band wordt "
                         "gecorrigeerd met een vaste 1,3 dB en is slechts een grenswaarde, "
                         "waardoor het luchtgeluidresultaat te laag of het contactgeluidresultaat "
                         "te hoog kan uitvallen. Of aan de eis voldaan is, kan niet met zekerheid "
                         "worden vastgesteld.")
        elif limit and all(e.check.status in ("complies", "tolerance", "fails") for e in limit):
            items.append("Banden die dicht bij het achtergrondgeluiddrukniveau liggen (6 dB of minder "
                         "erboven) worden gecorrigeerd met een vaste 1,3 dB en zijn slechts "
                         "grenswaarden; ze hebben het resultaat van de metingen waarin ze "
                         "voorkomen niet be\u00efnvloed.")
        elif limit:
            items.append(_LIMIT_NEUTRAL)
    elif limit:
        items.append(_LIMIT_NEUTRAL)
    if any(e.ok and any(len(v) > 1 for k, v in e.result.names.items() if k != "background")
           for e in evs):
        items.append("Waar meerdere meetposities zijn gebruikt, zijn de geluiddrukniveaus energetisch "
                     "gemiddeld; meerdere nagalmtijdverlopen zijn rekenkundig gemiddeld.")
    items += _remark_fallbacks(all_evs, options)
    if not items:
        return []
    return [Spacer(1, 4 * mm), Paragraph(T.SECTION_NOTES, st["h2"])] + \
        [Paragraph(f"\u2022 {t}", st["small"]) for t in items]


def _remark_fallbacks(evs: list, options: ReportOptions) -> list[str]:
    """With the remarks per measurement switched off: what the standards require and no other
    part of the report shows, named per measurement (ISO 16283-1/-2 clause 14: limit values;
    ISO 10052 6.2.1: overestimated installation noise; measurements without a result)."""
    if options.measurement_remarks:
        return []
    out = []

    def names(sel):
        return ", ".join(T.display_name(e) for e in sel)

    insulation = [e for e in evs if e.ok and e.kind != "installation"]
    installation = [e for e in evs if e.ok and e.kind == "installation"]
    if not (options.per_measurement_pages or options.per_band_tables):
        limit = [e for e in insulation if e.result.n_limit]
        if limit:
            out.append(T.FALLBACK_LIMIT.format(names=names(limit)))
    if not options.per_measurement_pages:
        over = [e for e in installation if e.result.background_affected]
        no_bg = [e for e in installation if e.result.background is None]
        if over:
            out.append(T.FALLBACK_OVER.format(names=names(over)))
        if no_bg:
            out.append(T.FALLBACK_NO_BG.format(names=names(no_bg)))
    failed = [e for e in evs if not e.ok]
    if failed:
        out.append(T.FALLBACK_ERROR.format(items="; ".join(
            f"{T.display_name(e)} ({T.note_text(e.error)})" for e in failed)))
    return [txt(t) for t in out]


_LIMIT_NEUTRAL = ("Banden die dicht bij het achtergrondgeluiddrukniveau liggen (6 dB of minder erboven) "
                  "worden gecorrigeerd met een vaste 1,3 dB en zijn slechts grenswaarden "
                  "(gearceerd in de tabellen). Ze kunnen het luchtgeluidresultaat te laag of het "
                  "contactgeluidresultaat te hoog doen uitvallen.")


def _bar_charts(evs: list, colors: dict, project: Project, kind: str, options: ReportOptions,
                st: dict) -> list:
    if not evs:
        return []
    if kind == "installation":                  # the quantity is per measurement: in the label
        shown = " / ".join(sorted({e.basis_label for e in evs}))
    else:
        basis = (AIRBORNE_BASES[project.airborne_basis] if kind == "airborne"
                 else IMPACT_BASES[project.impact_basis])
        quantity = "DnT,w" if kind == "airborne" else "L'nT,w"
        # with requirements the bars show the value the requirement is checked against
        shown = basis if options.requirements else quantity
    title = f"{T.KIND_TITLE[kind]} \u2013 {shown}"

    def label(e):
        return f"{e.basis_label}: {e.label}" if kind == "installation" else e.label

    story = []
    for start in range(0, len(evs), BARS_PER_CHART):
        chunk = evs[start:start + BARS_PER_CHART]
        png = charts.bars_chart(
            [(label(e), colors[id(e)], e.assessed if options.requirements else e.value,
              e.requirement if options.requirements else None) for e in chunk],
            T.KIND_AXIS[kind], title, show_requirement=options.requirements)
        story.append(KeepTogether([_image(png)]))
    return story


def _curves_section(evs: list, colors: dict, dashed: dict, kind: str, options: ReportOptions,
                    st: dict) -> list:
    ok = [e for e in evs if e.ok]
    if not ok:
        return []
    name = "DnT" if kind == "airborne" else "L'nT"
    story = [PageBreak(), Paragraph(mk(T.CURVES_HEAD[kind]), st["h1"])]
    png = charts.curves_chart([(e.label, colors[id(e)], dashed[id(e)], e.curve,
                                e.result.status == "limit") for e in ok], f"{name} [dB]",
                              T.CURVES_TITLE[kind])
    story.append(_band_image(png))
    if options.per_band_tables:
        caption = T.BAND_TABLE_CAPTION
        if any((e.result.status == "limit").any() for e in ok):
            caption += T.BAND_TABLE_LIMITS
        story += [Spacer(1, 4 * mm),
                  Paragraph(mk(caption.format(name=name, sign=T.LIMIT_PREFIX[kind])), st["small"]),
                  Spacer(1, 1.5 * mm)]
        rows = [[Paragraph("", st["tinyhead"]), Paragraph(T.COL_MEASUREMENT, st["tinyhead"])] +
                [Paragraph(b, st["tinyhead"]) for b in charts.BAND_LABELS]]
        extra = []
        for i, e in enumerate(ok, start=1):
            limit = e.result.status == "limit"
            rows.append([Paragraph("", st["tiny"]), Paragraph(txt(e.label), st["tiny"])] +
                        # no room for the sign in these narrow cells: the shading and the
                        # caption say that it is a limit value
                        [Paragraph(num(v), st["tinyc"]) for v in e.curve])
            extra.append(("BACKGROUND", (0, i), (0, i), rl.HexColor(colors[id(e)])))
            for b in np.nonzero(limit)[0]:
                extra.append(("BACKGROUND", (2 + b, i), (2 + b, i), rl.HexColor(LIMIT_BG)))
        extra += [("LEFTPADDING", (0, 0), (-1, -1), 1.5), ("RIGHTPADDING", (0, 0), (-1, -1), 1.5)]
        story.append(_table(rows, [3, 47] + [7.75] * 16, st, extra=extra))
    return story


class PhotoCache:
    """Each photo is shrunk once, however often the report shows it."""

    def __init__(self):
        self._cache: dict = {}

    def get(self, photo) -> PreparedPhoto | None:
        if photo.path not in self._cache:
            self._cache[photo.path] = prepare_photo(photo.path, photo.caption)
        found = self._cache[photo.path]
        if found is not None:
            found.caption = photo.caption
        return found


def _photo_image(ph: PreparedPhoto, max_w_mm: float, max_h_mm: float) -> Image:
    scale = min(max_w_mm / ph.width, max_h_mm / ph.height)
    return Image(io.BytesIO(ph.data), width=ph.width * scale * mm, height=ph.height * scale * mm)


def _rooms_used(evs: list) -> list:
    """Names of the rooms the included measurements refer to, in natural order."""
    names = {n for e in evs for n in (e.source_room, e.receiver_room) if n}
    return sorted(names, key=natural_key)


def _room_roles(evs: list, room: str) -> str:
    src = sum(1 for e in evs if e.kind in ("airborne", "installation") and e.source_room == room)
    tap = sum(1 for e in evs if e.kind == "impact" and e.source_room == room)
    rec = sum(1 for e in evs if e.receiver_room == room)
    parts = []
    # the room with the tapping machine is a source room too: one count for both
    for n, role in ((rec, "receiver"), (src + tap, "source")):
        if n:
            parts.append(f"{T.ROOM_ROLE[role]} bij {T.count_metingen(n)}")
    return ", ".join(parts)


def _rooms_section(project: Project, evs: list, cache: PhotoCache, st: dict) -> list:
    """A page with the photos of the rooms that the measurements are about."""
    rooms = [r for n in _rooms_used(evs) if (r := project.room(n)) and r.photos]
    if not rooms:
        return []
    story = [PageBreak(), Paragraph(T.SECTION_ROOMS, st["h1"]),
             Paragraph(T.ROOMS_INTRO, st["small"]), Spacer(1, 2 * mm)]
    half = FRAME_W / 2
    for room in rooms:
        cells = []
        for photo in room.photos:
            prepared = cache.get(photo)
            if prepared is None:
                cells.append([Paragraph(
                    f"<i>{T.PHOTO_UNREADABLE.format(name=txt(Path(photo.path).name))}</i>",
                    st["small"])])
                continue
            cell = [_photo_image(prepared, half / mm - 6, 60)]
            cell.append(Paragraph(txt(photo.caption), st["small"]) if photo.caption
                        else Spacer(1, 1))
            cells.append(cell)
        rows = [cells[i:i + 2] + [""] * (2 - len(cells[i:i + 2])) for i in range(0, len(cells), 2)]
        grid = Table(rows, colWidths=[half, half])
        grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                  ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                                  ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        head = [Paragraph(txt(room.name), st["h2"])]
        usage = _room_roles(evs, room.name)
        if usage:
            head.append(Paragraph(usage[0].upper() + usage[1:], st["small"]))
        head.append(Spacer(1, 1.5 * mm))
        story.append(KeepTogether(head + [grid]) if len(rows) <= 2 else head[0])
        if len(rows) > 2:
            story += head[1:] + [grid]
        story.append(Spacer(1, 3 * mm))
    return story


def _room_cells(ev: Evaluated, project: Project, cache: PhotoCache, st: dict,
                max_w_mm: float, max_h_mm: float) -> list:
    """Main photo, name and caption of the source / tapping room and of the receiving room:
    one list of flowables per room; [] when neither room has a photo."""
    wanted = [(T.ROOM_LABEL["receiver"], ev.receiver_room)]
    if ev.source_room:
        wanted.insert(0, (T.ROOM_LABEL["tapping" if ev.kind == "impact" else "source"],
                          ev.source_room))
    cells, any_photo = [], False
    for label, name in wanted:
        room = project.room(name)
        prepared = cache.get(room.photos[0]) if room and room.photos else None
        cell = []
        if prepared is not None:
            any_photo = True
            cell.append(_photo_image(prepared, max_w_mm, max_h_mm))
        cell.append(Paragraph(f"<b>{label}:</b> {txt(name)}", st["small"]))
        if prepared is not None and prepared.caption:
            cell.append(Paragraph(f"<i>{txt(prepared.caption)}</i>", st["small"]))
        cells.append(cell)
    return cells if any_photo else []


class ChartWithPhotos(Flowable):
    """A band chart with the room photos drawn in its free bottom right corner, under the
    legend (charts.rating_chart(ev, reserve_mm) keeps that corner free). This keeps a
    measurement on one page although the chart has the fixed scale of ISO 16283."""
    GAP = 3 * mm

    def __init__(self, chart: Image, cells: list):
        super().__init__()
        self.chart, self.cells = chart, cells
        self.cell_w = (charts.SIDE_W_MM * mm - self.GAP) / 2

    @staticmethod
    def block_height(cells: list, cell_w: float) -> float:
        """Height (points) of the tallest room cell at the given width."""
        return max(sum(f.wrap(cell_w, 1e6)[1] for f in cell) for cell in cells)

    def wrap(self, avail_w, avail_h):
        return self.chart.drawWidth, self.chart.drawHeight

    def draw(self):
        self.chart.drawOn(self.canv, 0, 0)
        top = self.block_height(self.cells, self.cell_w)      # cells hang from the same line
        for i, cell in enumerate(self.cells):
            x, y = charts.SIDE_X_MM * mm + i * (self.cell_w + self.GAP), top
            for f in cell:
                _, h = f.wrap(self.cell_w, 1e6)
                y -= h
                f.drawOn(self.canv, x, y)


def _chart_with_photos(ev: Evaluated, project: Project, cache: PhotoCache | None,
                       st: dict) -> Image | ChartWithPhotos:
    cells = _room_cells(ev, project, cache, st, 34, 24) if cache is not None else []
    if not cells:
        return _band_image(charts.rating_chart(ev))
    cell_w = (charts.SIDE_W_MM * mm - ChartWithPhotos.GAP) / 2
    reserve = ChartWithPhotos.block_height(cells, cell_w) / mm
    return ChartWithPhotos(_band_image(charts.rating_chart(ev, reserve_mm=reserve)), cells)


def _room_strip(ev: Evaluated, project: Project, cache: PhotoCache, st: dict) -> list:
    """Small main photo of the source room and the receiving room above the level history."""
    cells = _room_cells(ev, project, cache, st, 56, 32)
    if not cells:
        return []
    half = FRAME_W / 2
    t = Table([cells + [""] * (2 - len(cells))], colWidths=[half, half])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return [Spacer(1, 2 * mm), t, Spacer(1, 2 * mm)]


def when_text(moment) -> str:
    """'22/09/2026 12:06' (the files keep the time with a resolution of two seconds)."""
    return "" if moment is None else moment.strftime("%d/%m/%Y %H:%M")


def _file_text(ev: Evaluated, role: str, dates: bool = True) -> str:
    """The files of one role, each (optionally) with the date and time of its measurement."""
    infos = (ev.result.info or {}).get(role)
    if not infos:                                         # results built without file info
        return txt(", ".join(ev.result.names[role]))
    parts = []
    for i in infos:
        when = when_text(i.measured_at) if dates else ""
        parts.append(f"{txt(i.name)} ({when})" if when else txt(i.name))
    return "<br/>".join(parts)


def _file_lines(ev: Evaluated, st: dict, dates: bool = True) -> list:
    if ev.kind == "installation":         # level files first, then background and reverberation
        roles = [k for k in ("level", "background", "rt") if k in ev.result.info]
    else:
        roles = list(ev.result.names)
    rows = [[Paragraph(f"<b>{ROLE_TEXT[k]}</b>", st["small"]),
             Paragraph(_file_text(ev, k, dates), st["small"])] for k in roles]
    # wide enough for 'Contactgeluiddrukniveaus ontvangstruimte' on one line
    t = Table(rows, colWidths=[72 * mm, FRAME_W - 72 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    return [Paragraph(T.FILES_TITLE_DATES if dates else T.FILES_TITLE, st["h2"]), t]


def _equipment_section(project: Project, evs: list, st: dict) -> list:
    """The measuring instruments found in the files, plus free text for other equipment."""
    used = equipment_used(evs)
    other = [ln.strip() for ln in project.report.equipment.splitlines() if ln.strip()]
    if not used and not other:
        return []
    story = [Paragraph(T.SECTION_EQUIPMENT, st["h1"])]
    if used:
        rows = [[Paragraph(h, st["head"]) for h in T.EQUIP_HEAD]]
        for instrument, serial, roles in used:
            rows.append([Paragraph(txt(instrument), st["cell"]), Paragraph(str(serial), st["cellc"]),
                         Paragraph(", ".join(ROLE_TEXT[r].lower() for r in roles), st["cell"])])
        story.append(_table(rows, [45, 30, FRAME_W / mm - 75], st))
    if other:
        story += [Spacer(1, 2 * mm)] + [Paragraph(f"\u2022 {txt(line)}", st["small"]) for line in other]
    return [KeepTogether(story)]                     # heading, table and list stay on one page


def _result_box(ev: Evaluated, color: str, left: list, options: ReportOptions, st: dict) -> Table:
    """The result at the top of a measurement page: value (left), requirement and check (right,
    only with requirements), a bar in the colour of the measurement."""
    chk = ev.check
    show_check = options.requirements and chk.status != "none"
    style = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("BOX", (0, 0), (-1, -1), 0.6, rl.HexColor("#b2babb")),
             ("LINEBEFORE", (0, 0), (0, -1), 4, rl.HexColor(color)),
             ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
    if show_check:
        cell, _ = _check_cell(ev, st)
        right = [Paragraph(mk(T.DETAIL_REQUIREMENT.format(basis=ev.basis_label,
                                                           requirement=_requirement_text(ev))),
                           st["cellbox"]), cell]            # space: the subscripts need it
        if ev.tolerance:                                     # NBN S 01-400 in-situ tolerance
            small = T.DETAIL_TOLERANCE_SMALL if ev.small_room else ""
            right.append(Paragraph(mk(T.DETAIL_TOLERANCE.format(tol=ev.tolerance) + small),
                                   st["cellc"]))
        box = Table([[left, right]], colWidths=[FRAME_W * 0.66, FRAME_W * 0.34])
        if CHECK_BG[chk.status]:
            style.append(("BACKGROUND", (1, 0), (1, 0), rl.HexColor(CHECK_BG[chk.status])))
    else:
        box = Table([[left]], colWidths=[FRAME_W])
    box.setStyle(TableStyle(style))
    return box


def _remarks(ev: Evaluated, options: ReportOptions, st: dict) -> list:
    notes = notes_shown(ev, options) if options.measurement_remarks else []
    if not notes:
        return []
    # one block, so the heading never stays behind alone at the bottom of a page
    return [KeepTogether([Paragraph(T.COL_REMARKS, st["h2"])] +
                         [Paragraph(f"\u2022 {txt(T.note_text(n))}", st["small"]) for n in notes])]


def _installation_page(ev: Evaluated, color: str, project: Project, options: ReportOptions,
                       st: dict, cache: PhotoCache | None = None) -> list:
    """One installation noise measurement: result, level history with the time window of each
    file, the values per file, the reverberation time behind k, the files and the remarks."""
    r = ev.result
    name = T.display_name(ev)
    story = [PageBreak(), Paragraph(txt(name[0].upper() + name[1:]), st["h1"])]
    level = T.INSTALL_LEVEL[r.quantity]
    detail = T.DETAIL_INSTALL.format(level=level, measured=num(r.level), k=num(r.k, 2),
                                     quantity=r.symbol, lnt=num(r.lnt))
    left = [Paragraph(mk(f"{r.symbol} = {r.value} dB"), st["big"]),
            Paragraph(mk(detail), st["small"])]
    if r.method != "integrated" or options.integrated_method_note:      # the switch covers it
        left.append(Paragraph(mk(T.METHOD_TEXT[r.method]), st["small"]))
    if r.background is not None:
        left.append(Paragraph(mk(T.DETAIL_INSTALL_BG.format(bg=num(r.background))), st["small"]))
    if not options.measurement_remarks:          # ISO 10052 6.2.1: keep this with the value
        if r.background is None:
            left.append(Paragraph(T.DETAIL_INSTALL_NO_BG, st["small"]))
        elif r.background_affected:
            left.append(Paragraph(T.DETAIL_INSTALL_OVER, st["small"]))
    story.append(_result_box(ev, color, left, options, st))
    strip = _room_strip(ev, project, cache, st) if cache is not None else []
    story += strip or [Spacer(1, 3 * mm)]

    # level history of every file, the window shaded
    for rec in r.recordings:
        try:
            f = read_svl(rec.path)
        except (OSError, SvlError):                   # was readable when it was evaluated
            continue
        end = f.duration_s if rec.end is None else rec.end
        png = charts.history_chart(f.laeq_per_second(), f.lafmax_per_second(), rec.start, end,
                                   T.HISTORY_TITLE.format(file=rec.path.name),
                                   height_in=1.6 if len(r.recordings) > 1 else 1.9)
        story += [_image(png), Spacer(1, 1 * mm)]

    # values per file
    head = [h.format(level=level) for h in T.INSTALL_HEAD]
    has_bg = r.margins is not None
    widths = [70, 26, 18, 28, 32] if has_bg else [88, 30, 22, 34]
    rows = [[Paragraph(head_text(h), st["colhead"]) for h in head[:len(widths)]]]
    extra = []
    for i, (rec, seconds, value) in enumerate(zip(r.recordings, r.durations, r.levels), start=1):
        last = rec.start + seconds                    # end of the window = file end if open
        window = T.install_window(rec.start, rec.end, last)
        cells = [Paragraph(txt(rec.path.name), st["cell"]), Paragraph(window, st["cellc"]),
                 Paragraph(str(seconds), st["cellc"]), Paragraph(num(value), st["cellc"])]
        if has_bg:
            margin = r.margins[i - 1]
            cells.append(Paragraph(num(margin), st["cellc"]))
            if margin < 6:
                extra.append(("BACKGROUND", (4, i), (4, i), rl.HexColor(LIMIT_BG)))
        rows.append(cells)
    story += [Spacer(1, 1.5 * mm), _table(rows, widths, st, extra=extra)]

    # reverberation time behind k
    rows = [[Paragraph(head_text(h), st["colhead"]) for h in T.INSTALL_RT_HEAD]]
    for octave, thirds in OCTAVE_THIRDS.items():
        values = []
        for hz in thirds:
            t20 = " (T20)" if hz in r.t20_used else ""
            values.append(f"{num(r.t_thirds[hz], 3)}{t20}")
        rows.append([Paragraph(str(octave), st["cellc"]),
                     Paragraph(", ".join(str(h) for h in thirds), st["cellc"]),
                     Paragraph(", ".join(values), st["cellc"]),
                     Paragraph(f"<b>{num(r.t_octaves[octave], 3)}</b>", st["cellc"])])
    story += [Spacer(1, 3 * mm), _table(rows, [26, 40, 70, 38], st),
              Spacer(1, 1.5 * mm), Paragraph(mk(T.DETAIL_INSTALL_RT), st["small"])]
    if options.measurement_files:
        story += _file_lines(ev, st, options.file_dates)
    story += _remarks(ev, options, st)
    return story


def _detail_page(ev: Evaluated, color: str, project: Project, options: ReportOptions,
                 terms: set, st: dict, cache: PhotoCache | None = None) -> list:
    r, rt = ev.result, ev.rating
    airborne = ev.kind == "airborne"
    name = T.display_name(ev)
    story = [PageBreak(), Paragraph(txt(name[0].upper() + name[1:]), st["h1"])]
    # result line: the quantity and the adaptation terms that are switched on
    if rt is None:
        missing = ", ".join(str(int(f)) for f in r.bands[~np.isfinite(ev.curve)])
        big = T.DETAIL_NO_RATING.format(missing=missing)
        detail = ""
    else:
        shown = [(n, v) for k, n, v in (("c", "C", r.c), ("ctr", "Ctr", r.ctr)) if k in terms] \
            if airborne else [("C_I", r.ci)] if "ci" in terms else []
        quantity = "DnT,w" if airborne else "L'nT,w"
        if shown:
            big = mk(f"{quantity} ({'; '.join(n for n, _ in shown)}) = {rt.value} "
                     f"({'; '.join(minus(v) for _, v in shown)}) dB")
        else:
            big = mk(f"{quantity} = {rt.value} dB")
        shift = f"{rt.shift:+d}".replace("-", "\u2212")
        detail = T.DETAIL_SHIFT.format(shift=shift, sum=num(rt.unfavourable_sum),
                                       t=r.t_kind.upper())
    left = [Paragraph(big, st["big"])]
    if detail:
        left.append(Paragraph(detail, st["small"]))
    left.append(Paragraph(mk(T.DETAIL_EVALUATION[ev.kind]), st["small"]))   # 16283 clause 14
    if options.uncertainty and ev.uncertainty is not None:                    # ISO 12999-1
        left.append(Paragraph(mk(T.DETAIL_UNCERTAINTY.format(
            quantity=ev.basis_label, value=minus(ev.assessed), u=num(ev.uncertainty))),
            st["small"]))
    story.append(_result_box(ev, color, left, options, st))
    # the room photos sit next to the chart, under its legend (not in a strip above it)
    story += [Spacer(1, 3 * mm), _chart_with_photos(ev, project, cache, st), Spacer(1, 2 * mm)]

    # values per band
    lim = r.status == "limit"
    head = T.AIRBORNE_HEAD if airborne else T.IMPACT_HEAD
    widths = [15.8] * 11 if airborne else [19.3] * 9
    rows = [[Paragraph(head_text(h), st["colhead"]) for h in head]]
    extra = []
    for i, hz in enumerate(BANDS):
        raw = r.l2_raw[i] if airborne else r.li_raw[i]
        corrected = r.l2[i] if airborne else r.li[i]
        delta = corrected - raw
        corr = "-" if abs(delta) < 1e-9 else num(delta) + ("*" if lim[i] else "")
        ref = "-" if rt is None else str(int(rt.curve[i]))
        dev = "-" if rt is None or rt.deviations[i] == 0 else num(rt.deviations[i])
        result = limit_text(ev.curve[i], lim[i], ev.kind)       # DnT >= ... / L'nT <= ...
        if airborne:
            vals = [str(int(hz)), num(r.l1[i]), num(raw), num(r.lb[i]), num(corrected), corr,
                    num(r.t[i], 3), num(r.d[i]), result, ref, dev]
        else:
            vals = [str(int(hz)), num(raw), num(r.lb[i]), num(corrected), corr, num(r.t[i], 3),
                    result, ref, dev]
        rows.append([Paragraph(v, st["cellc"]) for v in vals])
        if lim[i]:
            extra.append(("BACKGROUND", (0, i + 1), (-1, i + 1), rl.HexColor(LIMIT_BG)))
        if dev != "-":
            extra.append(("BACKGROUND", (len(vals) - 1, i + 1), (len(vals) - 1, i + 1),
                          rl.HexColor("#f5b7b1")))
    extra.append(("LEFTPADDING", (0, 0), (-1, -1), 2))
    extra.append(("RIGHTPADDING", (0, 0), (-1, -1), 2))
    # compact band rows: the chart above has a fixed scale (up to ~120 mm high for impact),
    # and result, chart, table and file list should still fit on one page
    extra.append(("TOPPADDING", (0, 1), (-1, -1), 0.8))
    extra.append(("BOTTOMPADDING", (0, 1), (-1, -1), 0.8))
    story.append(_table(rows, widths, st, extra=extra))
    small = [T.DETAIL_CORRECTION]
    if lim.any():
        small.append(T.DETAIL_LIMIT)
    story += [Spacer(1, 1.5 * mm)] + [Paragraph(t, st["small"]) for t in small]
    if options.measurement_files:
        story += _file_lines(ev, st, options.file_dates)
    story += _remarks(ev, options, st)
    return story


# ----------------------------------------------------------------------------- main entry
def build_pdf_report(project: Project, evaluated: list, path, options: ReportOptions | None = None,
                     hidden=()) -> Path:
    """Write the PDF report of the building to `path` and return the path.

    evaluated: result of calc.building.evaluate_project(project) (all measurements, in order).
    options: what the report contains (default: everything).
    hidden: set of (kind, name) of measurements to leave out, e.g. those unticked in the viewer.
    """
    _register_fonts()
    options = options or ReportOptions()
    date = options.date or dt.date.today()
    st = styles()
    cache = PhotoCache()
    colors, dashed = {}, {}
    for i, e in enumerate(evaluated):          # same colour per measurement as in the viewer
        colors[id(e)], dashed[id(e)] = style_of(i)
    evs = [e for e in evaluated if (e.kind, e.name) not in hidden]
    air = [e for e in evs if e.kind == "airborne"]
    imp = [e for e in evs if e.kind == "impact"]
    ins = [e for e in evs if e.kind == "installation"]

    story = _title_block(project, evs, date, options, st)
    if options.summary:
        story += _summary(evs, options, st)
    if air:
        story += [Paragraph(T.SECTION_AIRBORNE, st["h1"]),
                  _overview_table(air, "airborne", project, options, st)]
    if imp:
        story += [Paragraph(T.SECTION_IMPACT, st["h1"]),
                  _overview_table(imp, "impact", project, options, st)]
    if ins:
        story += [Paragraph(T.SECTION_INSTALLATION, st["h1"]),
                  _overview_table(ins, "installation", project, options, st)]
    if options.notes:
        story += _notes(evs, project, options, st)
    if options.equipment:
        story += _equipment_section(project, evs, st)
    if not evs:
        story.append(Paragraph(T.EMPTY, st["body"]))
    else:
        if options.room_photos:
            story += _rooms_section(project, evs, cache, st)
        story += [PageBreak(), Paragraph(T.SECTION_COMPARISON, st["h1"])]
        story += _bar_charts(air, colors, project, "airborne", options, st)
        story += _bar_charts(imp, colors, project, "impact", options, st)
        story += _bar_charts(ins, colors, project, "installation", options, st)
        story += _curves_section(air, colors, dashed, "airborne", options, st)
        story += _curves_section(imp, colors, dashed, "impact", options, st)
        if options.per_measurement_pages:
            photos = cache if options.room_photos else None
            for e in evs:
                if not e.ok:
                    continue
                if e.kind == "installation":
                    story += _installation_page(e, colors[id(e)], project, options, st, photos)
                else:
                    terms = shown_terms(options, project, evs, e.kind)
                    story += _detail_page(e, colors[id(e)], project, options, terms, st, photos)

    path = Path(path)
    doc = BaseDocTemplate(str(path), pagesize=PAGE,
                          title=T.DOC_TITLE.format(name=project.name),
                          author=project.report.author or "", subject=T.DOC_SUBJECT)
    # no frame padding: tables, pictures and text all start exactly at the margin
    frame = Frame(MARGIN_X, MARGIN_BOTTOM, FRAME_W, PAGE[1] - MARGIN_TOP - MARGIN_BOTTOM,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="main")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame])])
    doc.build(story, canvasmaker=_canvas_maker(project.name, _date_text(date)))
    return path
