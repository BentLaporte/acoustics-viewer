"""PDF report of a building: results, compliance, comparison and one page per measurement.

Built with reportlab (layout) and matplotlib (charts). The fonts are the DejaVu fonts that ship
with matplotlib, so characters like the arrow, >=, <= and the minus sign always work.
Nothing in here depends on the GUI.
"""
from __future__ import annotations

import datetime as dt
import io
import os
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib
import numpy as np
from reportlab.lib import colors as rl
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (BaseDocTemplate, Frame, Image, KeepTogether, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

from calc.building import (AIRBORNE_BASES, IMPACT_BASES, Evaluated, Project, equipment_used,
                           natural_key)
from calc.colors import style_of
from calc.iso717 import BANDS

from . import charts
from .photos import PreparedPhoto, prepare_photo

PAGE = A4
MARGIN_X, MARGIN_TOP, MARGIN_BOTTOM = 18 * mm, 16 * mm, 20 * mm
FRAME_W = PAGE[0] - 2 * MARGIN_X                       # 174 mm
FONT, FONT_B = "DejaVu", "DejaVu-Bold"
CHECK_BG = {"complies": "#d5f5e3", "fails": "#f5b7b1", "inconclusive": "#fdebd0",
            "no_result": "#eaecee", "none": None}
CHECK_FG = {"complies": "#1e8449", "fails": "#c0392b", "inconclusive": "#b9770e"}
LIMIT_BG = "#fdebd0"
HEAD_BG = "#2c3e50"
BAND_TEXT = ["100", "125", "160", "200", "250", "315", "400", "500", "630", "800", "1000",
             "1250", "1600", "2000", "2500", "3150"]
BARS_PER_CHART = 10
ROLE_TEXT = {"source": "Source room levels", "receiver": "Receiving room levels",
             "tapping": "Tapping machine levels", "background": "Background",
             "rt": "Reverberation time"}

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
_SUBSCRIPTS = [("DnT,w", "D<sub>nT,w</sub>"), ("L'nT,w", "L'<sub>nT,w</sub>"),
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


def num(v, nd: int = 1) -> str:
    return "-" if v is None or not np.isfinite(v) else f"{v:.{nd}f}".replace("-", "\u2212")


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


# ----------------------------------------------------------------------------- options
@dataclass
class ReportOptions:
    per_measurement_pages: bool = True      # one page with chart and band table per measurement
    per_band_tables: bool = True            # values per band under the comparison curves
    room_photos: bool = True                # photos page and small photos on measurement pages
    file_dates: bool = True                 # date and time of every measurement file
    date: dt.date | None = None             # report date, default today


def default_report_name(project: Project) -> str:
    safe = "".join(c for c in project.name if c not in '\\/:*?"<>|').strip() or "Building"
    return f"{safe} - report.pdf"


def _date_text(d: dt.date) -> str:
    return f"{d.day} {d.strftime('%B %Y')}"


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
            self.setFont(FONT, 7.2)
            self.setFillColor(rl.HexColor("#566573"))
            self.drawString(MARGIN_X, y, left[:80])
            self.drawCentredString(PAGE[0] / 2, y, f"Page {self._pageNumber} of {total}")
            self.drawRightString(PAGE[0] - MARGIN_X, y, right)

    return NumberedCanvas


# ----------------------------------------------------------------------------- content blocks
def _check_cell(ev: Evaluated, st: dict):
    c = ev.check
    if c.status == "none":
        return Paragraph("", st["cellc"]), None
    margin = "" if c.margin is None else \
        f"<br/>({c.margin:+d} dB)".replace("-", "\u2212")      # result on line 1, margin on line 2
    fg = CHECK_FG.get(c.status, "#424949")
    return Paragraph(f"<font color='{fg}'><b>{c.text}{margin}</b></font>", st["cellc"]), \
        CHECK_BG[c.status]


def _requirement_text(ev: Evaluated) -> str:
    if ev.requirement is None:
        return ""
    return f"{'\u2265' if ev.kind == 'airborne' else '\u2264'} {ev.requirement} dB"


def _overview_table(evs: list, kind: str, project: Project, st: dict) -> Table:
    basis = (AIRBORNE_BASES[project.airborne_basis] if kind == "airborne"
             else IMPACT_BASES[project.impact_basis])
    if kind == "airborne":
        head = ["Measurement", "DnT,w", "C", "Ctr", f"Requirement ({basis})", "Check", "Remarks"]
        widths = [52, 12, 8, 9, 22, 30, 41]
    else:
        head = ["Measurement (tapping room \u2192 receiving room)", "L'nT,w", "C_I",
                f"Requirement ({basis})", "Check", "Remarks"]
        widths = [52, 13, 8, 24, 30, 47]
    rows = [[Paragraph(mk(h), st["head"]) for h in head]]
    extra = []
    for i, ev in enumerate(evs, start=1):
        r = ev.result
        value = str(ev.value) if ev.value is not None else "-"
        if kind == "airborne":
            nums = [value, minus(r.c) if r and r.c is not None else "-",
                    minus(r.ctr) if r and r.ctr is not None else "-"]
        else:
            nums = [value, minus(r.ci) if r and r.ci is not None else "-"]
        check, bg = _check_cell(ev, st)
        row = [Paragraph(txt(ev.label), st["cell"]),
               Paragraph(f"<b>{nums[0]}</b>", st["cellb"])]
        row += [Paragraph(n, st["cellc"]) for n in nums[1:]]
        row += [Paragraph(_requirement_text(ev), st["cellc"]), check,
                Paragraph(txt("; ".join(ev.notes)), st["small"])]
        rows.append(row)
        if bg:
            extra.append(("BACKGROUND", (len(nums) + 2, i), (len(nums) + 2, i),
                          rl.HexColor(bg)))
        if not ev.ok:
            extra.append(("BACKGROUND", (0, i), (0, i), rl.HexColor("#fadbd8")))
    return _table(rows, widths, st, extra=extra)


def _counts(evs) -> dict:
    c = {"complies": 0, "fails": 0, "inconclusive": 0, "no_result": 0, "none": 0}
    for e in evs:
        c[e.check.status] += 1
    return c


def _title_block(project: Project, evs: list, date: dt.date, st: dict) -> list:
    info = project.report
    story = [Paragraph("Sound insulation measurements", st["title"]),
             Paragraph(txt(project.name), st["subtitle"]), Spacer(1, 5 * mm)]
    rt = {"t30": "T30 (RT30)", "t20": "T20 (RT20)", "edt": "EDT"}[project.rt_kind]
    facts = []
    if info.client:
        facts.append(("Client", txt(info.client)))
    if info.location:
        facts.append(("Location", txt(info.location)))
    if info.author:
        facts.append(("Prepared by", txt(info.author)))
    facts.append(("Report date", _date_text(date)))
    facts.append(("Reverberation time used", rt))
    kinds = {e.kind for e in evs}
    basis = []
    if "airborne" in kinds:
        basis.append(f"airborne: {AIRBORNE_BASES[project.airborne_basis]}")
    if "impact" in kinds:
        basis.append(f"impact: {IMPACT_BASES[project.impact_basis]}")
    if any(e.requirement is not None for e in evs) and basis:
        facts.append(("Requirements checked against", mk("; ".join(basis))))
    rows = [[Paragraph(f"<b>{k}</b>", st["body"]), Paragraph(v, st["body"])] for k, v in facts]
    t = Table(rows, colWidths=[52 * mm, FRAME_W - 52 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LINEBELOW", (0, 0), (-1, -1), 0.3, rl.HexColor("#d5d8dc")),
                           ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(t)
    if info.remarks.strip():
        story += [Spacer(1, 4 * mm), Paragraph("<b>Remarks</b>", st["body"])]
        story += [Paragraph(txt(line), st["body"]) for line in info.remarks.strip().splitlines()
                  if line.strip()]
    return story


def _summary(evs: list, st: dict) -> list:
    n_air = sum(1 for e in evs if e.kind == "airborne")
    n_imp = len(evs) - n_air
    c = _counts(evs)
    parts = []
    if n_air:
        parts.append(f"{n_air} airborne")
    if n_imp:
        parts.append(f"{n_imp} impact")
    text = f"<b>{len(evs)} measurement(s)</b> ({', '.join(parts)}). "
    if len(evs) - c["none"]:
        bits = [f"<font color='{CHECK_FG['complies']}'><b>{c['complies']} comply</b></font>",
                f"<font color='{CHECK_FG['fails']}'><b>{c['fails']} do not comply</b></font>"]
        if c["inconclusive"]:
            bits.append(f"<font color='{CHECK_FG['inconclusive']}'><b>{c['inconclusive']} not "
                        "conclusive</b></font>")
        if c["no_result"]:
            bits.append(f"{c['no_result']} without result")
        if c["none"]:
            bits.append(f"{c['none']} without requirement")
        text += "Requirements: " + ", ".join(bits) + "."
    else:
        text += "No requirements were set."
    return [Spacer(1, 5 * mm), Paragraph(text, st["body"])]


def _notes(evs: list, project: Project, st: dict) -> list:
    kinds = {e.kind for e in evs}
    items = []
    if "airborne" in kinds:
        items.append(mk("DnT,w is the weighted standardized level difference between two rooms "
                        "(higher is better); C and Ctr are the spectrum adaptation terms. They "
                        "are determined from the one-third octave band levels from 100 to 3150 "
                        "Hz according to ISO 717-1."))
    if "impact" in kinds:
        items.append(mk("L'nT,w is the weighted standardized impact sound pressure level "
                        "(lower is better); C_I is the spectrum adaptation term (100 to 2500 Hz) "
                        "according to ISO 717-2."))
    if any(e.requirement is not None for e in evs):
        items.append("Airborne results must be at least the required value and impact results "
                     "at most the required value. The margin is the difference in dB "
                     "(positive = better than required).")
    if any(e.check.status == "inconclusive" for e in evs):
        items.append("Not conclusive: one or more one-third octave bands lie close to the "
                     "background level (less than 6 dB above it). Such a band is corrected by a "
                     "fixed 1.3 dB and is only a limit value, which can make the airborne "
                     "result too low or the impact result too high. Compliance cannot be "
                     "decided with certainty.")
    elif any(e.ok and e.result.n_limit for e in evs):
        items.append("Bands that lie close to the background level (less than 6 dB above it) "
                     "are corrected by a fixed 1.3 dB and are only limit values; they did not "
                     "affect the result of the measurements they occur in.")
    if any(e.ok and any(len(v) > 1 for k, v in e.result.names.items() if k != "background")
           for e in evs):
        items.append("Where several measurement positions were used, the levels were "
                     "energy-averaged; several reverberation time decays were averaged "
                     "arithmetically.")
    return [Spacer(1, 4 * mm), Paragraph("Notes", st["h2"])] + \
        [Paragraph(f"\u2022 {t}", st["small"]) for t in items]


def _bar_charts(evs: list, colors: dict, project: Project, kind: str, st: dict) -> list:
    if not evs:
        return []
    basis = (AIRBORNE_BASES[project.airborne_basis] if kind == "airborne"
             else IMPACT_BASES[project.impact_basis])
    axis = "higher is better" if kind == "airborne" else "lower is better"
    title = {"airborne": "Airborne sound insulation", "impact": "Impact sound"}[kind] + \
        f" \u2013 {basis}"
    story = []
    for start in range(0, len(evs), BARS_PER_CHART):
        chunk = evs[start:start + BARS_PER_CHART]
        png = charts.bars_chart([(e.label, colors[id(e)], e.assessed, e.requirement)
                                 for e in chunk], axis, title)
        story.append(KeepTogether([_image(png)]))
    return story


def _curves_section(evs: list, colors: dict, dashed: dict, kind: str, options: ReportOptions,
                    st: dict) -> list:
    ok = [e for e in evs if e.ok]
    if not ok:
        return []
    name = "DnT" if kind == "airborne" else "L'nT"
    title = {"airborne": "Standardized level difference DnT",
             "impact": "Standardized impact sound pressure level L'nT"}[kind]
    head = {"airborne": "Airborne: DnT per band", "impact": "Impact: L'nT per band"}[kind]
    story = [PageBreak(), Paragraph(mk(head), st["h1"])]
    png = charts.curves_chart([(e.label, colors[id(e)], dashed[id(e)], e.curve,
                                e.result.status == "limit") for e in ok], f"{name} [dB]", title)
    story.append(_image(png))
    if options.per_band_tables:
        story += [Spacer(1, 4 * mm),
                  Paragraph(mk(f"{name} per one-third octave band [dB]; bands close to the "
                               "background are shaded"), st["small"]), Spacer(1, 1.5 * mm)]
        rows = [[Paragraph("", st["tinyhead"]), Paragraph("Measurement", st["tinyhead"])] +
                [Paragraph(b, st["tinyhead"]) for b in charts.BAND_LABELS]]
        extra = []
        for i, e in enumerate(ok, start=1):
            limit = e.result.status == "limit"
            rows.append([Paragraph("", st["tiny"]), Paragraph(txt(e.label), st["tiny"])] +
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
    src = sum(1 for e in evs if e.kind == "airborne" and e.source_room == room)
    tap = sum(1 for e in evs if e.kind == "impact" and e.source_room == room)
    rec = sum(1 for e in evs if e.receiver_room == room)
    def count(n: int) -> str:
        return f"{n} measurement" + ("" if n == 1 else "s")

    parts = []
    if rec:
        parts.append(f"receiving room in {count(rec)}")
    if src:
        parts.append(f"source room in {count(src)}")
    if tap:
        parts.append(f"tapping room in {count(tap)}")
    return ", ".join(parts)


def _rooms_section(project: Project, evs: list, cache: PhotoCache, st: dict) -> list:
    """A page with the photos of the rooms that the measurements are about."""
    rooms = [r for n in _rooms_used(evs) if (r := project.room(n)) and r.photos]
    if not rooms:
        return []
    story = [PageBreak(), Paragraph("Rooms", st["h1"]),
             Paragraph("Photos of the rooms the measurements refer to.", st["small"]),
             Spacer(1, 2 * mm)]
    half = FRAME_W / 2
    for room in rooms:
        cells = []
        for photo in room.photos:
            prepared = cache.get(photo)
            if prepared is None:
                cells.append([Paragraph(f"<i>Photo could not be read: {txt(Path(photo.path).name)}"
                                        "</i>", st["small"])])
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


def _room_strip(ev: Evaluated, project: Project, cache: PhotoCache, st: dict) -> list:
    """Small main photo of the source / tapping room and the receiving room above the chart."""
    wanted = [("Receiving room", ev.receiver_room)]
    if ev.source_room:
        wanted.insert(0, ("Source room" if ev.kind == "airborne" else "Tapping room",
                          ev.source_room))
    cells, any_photo = [], False
    for label, name in wanted:
        room = project.room(name)
        prepared = cache.get(room.photos[0]) if room and room.photos else None
        cell = []
        if prepared is not None:
            any_photo = True
            cell.append(_photo_image(prepared, 62, 38))
        cell.append(Paragraph(f"<b>{label}:</b> {txt(name)}", st["small"]))
        if prepared is not None and prepared.caption:
            cell.append(Paragraph(f"<i>{txt(prepared.caption)}</i>", st["small"]))
        cells.append(cell)
    if not any_photo:
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
    rows = [[Paragraph(f"<b>{ROLE_TEXT[k]}</b>", st["small"]),
             Paragraph(_file_text(ev, k, dates), st["small"])] for k in ev.result.names]
    t = Table(rows, colWidths=[42 * mm, FRAME_W - 42 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    title = "Measurement files" + (" (date and time of the measurement)" if dates else "")
    return [Paragraph(title, st["h2"]), t]


def _equipment_section(project: Project, evs: list, st: dict) -> list:
    """The measuring instruments found in the files, plus free text for other equipment."""
    used = equipment_used(evs)
    other = [ln.strip() for ln in project.report.equipment.splitlines() if ln.strip()]
    if not used and not other:
        return []
    story = [Paragraph("Equipment", st["h1"])]
    if used:
        rows = [[Paragraph(h, st["head"]) for h in ("Instrument", "Serial number", "Used for")]]
        for instrument, serial, roles in used:
            rows.append([Paragraph(txt(instrument), st["cell"]), Paragraph(str(serial), st["cellc"]),
                         Paragraph(", ".join(ROLE_TEXT[r].lower() for r in roles), st["cell"])])
        story.append(_table(rows, [45, 30, FRAME_W / mm - 75], st))
    if other:
        story += [Spacer(1, 2 * mm)] + [Paragraph(f"\u2022 {txt(line)}", st["small"]) for line in other]
    return [KeepTogether(story)]                     # heading, table and list stay on one page


def _detail_page(ev: Evaluated, color: str, project: Project, st: dict,
                 cache: PhotoCache | None = None, dates: bool = True) -> list:
    r, rt = ev.result, ev.rating
    airborne = ev.kind == "airborne"
    story = [PageBreak(), Paragraph(txt(ev.name), st["h1"])]
    # result line
    if rt is None:
        missing = ", ".join(str(int(f)) for f in r.bands[~np.isfinite(ev.curve)])
        big = f"Rating not possible (no reverberation time at {missing} Hz)"
        detail = ""
    else:
        if airborne:
            big = mk(f"DnT,w (C; Ctr) = {rt.value} ({minus(r.c)}; {minus(r.ctr)}) dB")
        else:
            big = mk(f"L'nT,w (C_I) = {rt.value} ({minus(r.ci)}) dB")
        shift = f"{rt.shift:+d}".replace("-", "\u2212")
        detail = (f"Reference curve shifted {shift} dB; sum of unfavourable deviations "
                  f"{rt.unfavourable_sum:.1f} dB (maximum 32.0 dB); T = {r.t_kind.upper()}.")
    left = [Paragraph(big, st["big"])]
    if detail:
        left.append(Paragraph(detail, st["small"]))
    chk = ev.check
    right = []
    if chk.status != "none":
        cell, _ = _check_cell(ev, st)
        right = [Paragraph(mk(f"Requirement {ev.basis_label} {_requirement_text(ev)}"),
                           st["cellc"]), cell]
    box = Table([[left, right]], colWidths=[FRAME_W * 0.66, FRAME_W * 0.34])
    style = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BOX", (0, 0), (-1, -1), 0.6,
                                                     rl.HexColor("#b2babb")),
             ("LINEBEFORE", (0, 0), (0, -1), 4, rl.HexColor(color)),
             ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
    if CHECK_BG[chk.status]:
        style.append(("BACKGROUND", (1, 0), (1, 0), rl.HexColor(CHECK_BG[chk.status])))
    box.setStyle(TableStyle(style))
    story.append(box)
    strip = _room_strip(ev, project, cache, st) if cache is not None else []
    story += strip or [Spacer(1, 3 * mm)]
    story += [_image(charts.rating_chart(ev, height_in=2.5 if strip else 2.9)), Spacer(1, 2 * mm)]

    # values per band
    lim = r.status == "limit"
    if airborne:
        head = ["Band\n[Hz]", "L1\n[dB]", "L2\nmeasured", "Lb\n[dB]", "L2\ncorrected",
                "Correc-\ntion [dB]", "T [s]", "D\n[dB]", "DnT\n[dB]", "Ref.\ncurve",
                "Unfav.\ndev."]
        widths = [15.8] * 11
    else:
        head = ["Band\n[Hz]", "Li\nmeasured", "Lb\n[dB]", "Li\ncorrected", "Correc-\ntion [dB]",
                "T [s]", "L'nT\n[dB]", "Ref.\ncurve", "Unfav.\ndev."]
        widths = [19.3] * 9
    rows = [[Paragraph(head_text(h), st["colhead"]) for h in head]]
    extra = []
    for i, hz in enumerate(BANDS):
        raw = r.l2_raw[i] if airborne else r.li_raw[i]
        corrected = r.l2[i] if airborne else r.li[i]
        delta = corrected - raw
        corr = "-" if abs(delta) < 1e-9 else num(delta) + ("*" if lim[i] else "")
        ref = "-" if rt is None else str(int(rt.curve[i]))
        dev = "-" if rt is None or rt.deviations[i] == 0 else num(rt.deviations[i])
        if airborne:
            vals = [str(int(hz)), num(r.l1[i]), num(raw), num(r.lb[i]), num(corrected), corr,
                    num(r.t[i], 3), num(r.d[i]), num(r.dnt[i]), ref, dev]
        else:
            vals = [str(int(hz)), num(raw), num(r.lb[i]), num(corrected), corr, num(r.t[i], 3),
                    num(r.lnt[i]), ref, dev]
        rows.append([Paragraph(v, st["cellc"]) for v in vals])
        if lim[i]:
            extra.append(("BACKGROUND", (0, i + 1), (-1, i + 1), rl.HexColor(LIMIT_BG)))
        if dev != "-":
            extra.append(("BACKGROUND", (len(vals) - 1, i + 1), (len(vals) - 1, i + 1),
                          rl.HexColor("#f5b7b1")))
    extra.append(("LEFTPADDING", (0, 0), (-1, -1), 2))
    extra.append(("RIGHTPADDING", (0, 0), (-1, -1), 2))
    story.append(_table(rows, widths, st, extra=extra))
    small = ["Correction = background noise correction applied to the level of the receiving room."]
    if lim.any():
        small.append("* Band less than 6 dB above the background: corrected by a fixed 1.3 dB and "
                     "only a limit value (shaded).")
    story += [Spacer(1, 1.5 * mm)] + [Paragraph(t, st["small"]) for t in small]
    story += _file_lines(ev, st, dates)
    if ev.notes:
        story += [Paragraph("Remarks", st["h2"])] + \
            [Paragraph(f"\u2022 {txt(n)}", st["small"]) for n in ev.notes]
    return story


# ----------------------------------------------------------------------------- main entry
def build_pdf_report(project: Project, evaluated: list, path, options: ReportOptions | None = None,
                     hidden=()) -> Path:
    """Write the PDF report of the building to `path` and return the path.

    evaluated: result of calc.building.evaluate_project(project) (all measurements, in order).
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

    story = _title_block(project, evs, date, st) + _summary(evs, st)
    if air:
        story += [Paragraph("Airborne sound insulation", st["h1"]),
                  _overview_table(air, "airborne", project, st)]
    if imp:
        story += [Paragraph("Impact sound", st["h1"]),
                  _overview_table(imp, "impact", project, st)]
    story += _notes(evs, project, st)
    story += _equipment_section(project, evs, st)
    if not evs:
        story.append(Paragraph("There are no measurements in this building yet.", st["body"]))
    else:
        if options.room_photos:
            story += _rooms_section(project, evs, cache, st)
        story += [PageBreak(), Paragraph("Comparison", st["h1"])]
        story += _bar_charts(air, colors, project, "airborne", st)
        story += _bar_charts(imp, colors, project, "impact", st)
        story += _curves_section(air, colors, dashed, "airborne", options, st)
        story += _curves_section(imp, colors, dashed, "impact", options, st)
        if options.per_measurement_pages:
            for e in evs:
                if e.ok:
                    story += _detail_page(e, colors[id(e)], project, st,
                                          cache if options.room_photos else None,
                                          options.file_dates)

    path = Path(path)
    doc = BaseDocTemplate(str(path), pagesize=PAGE,
                          title=f"{project.name} - sound insulation measurements",
                          author=project.report.author or "", subject="Sound insulation")
    # no frame padding: tables, pictures and text all start exactly at the margin
    frame = Frame(MARGIN_X, MARGIN_BOTTOM, FRAME_W, PAGE[1] - MARGIN_TOP - MARGIN_BOTTOM,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="main")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame])])
    doc.build(story, canvasmaker=_canvas_maker(project.name, _date_text(date)))
    return path
