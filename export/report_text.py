"""All Dutch wording of the PDF report in one place.

Everything the reader of the report sees that is not user data (names, remarks) comes from here
or from the small helpers below, so a wording change never means hunting through the layout
code. Quantity symbols (DnT,w, L'nT,w, C, Ctr, C_I) are international and stay as they are;
`pdf_report.mk` sets their subscripts.

Numbers use a decimal comma ('67,5'), dates are written out in Dutch ('8 oktober 2026').
"""
from __future__ import annotations

import datetime as dt
import re

import numpy as np

MONTHS = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus",
          "september", "oktober", "november", "december"]

# ----------------------------------------------------------------------------- numbers, dates


def comma(text: str) -> str:
    """'67.5' -> '67,5' (decimal comma). Only for text that is a number or a plain number list."""
    return text.replace(".", ",")


def number(value, nd: int = 1) -> str:
    """A level or time with a decimal comma and a real minus sign; '-' for a missing value."""
    if value is None or not np.isfinite(value):
        return "-"
    return comma(f"{value:.{nd}f}").replace("-", "\u2212")


def date_text(d: dt.date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


# ----------------------------------------------------------------------------- fixed texts
TITLE = "Geluidsisolatiemetingen"
EMPTY = "Er zijn nog geen metingen in dit gebouw."
PAGE_OF = "Pagina {page} van {total}"

FACT_CLIENT, FACT_LOCATION, FACT_AUTHOR = "Opdrachtgever", "Locatie", "Opgesteld door"
FACT_DATE = "Rapportdatum"
FACT_RT = "Gebruikte nagalmtijd"
FACT_BASIS = "Eisen getoetst aan"
REMARKS = "Opmerkingen"
SECTION_AIRBORNE, SECTION_IMPACT = "Luchtgeluidisolatie", "Contactgeluiddrukniveau"
SECTION_COMPARISON = "Vergelijking"
SECTION_EQUIPMENT = "Apparatuur"
SECTION_NOTES = "Toelichting"
SECTION_ROOMS = "Ruimten"
ROOMS_INTRO = "Foto's van de ruimten waarop de metingen betrekking hebben."

KIND_WORD = {"airborne": "luchtgeluid", "impact": "contactgeluid"}
KIND_TITLE = {"airborne": "Luchtgeluidisolatie", "impact": "Contactgeluiddrukniveau"}
KIND_AXIS = {"airborne": "hoger is beter", "impact": "lager is beter"}
CURVES_HEAD = {"airborne": "Luchtgeluid: DnT per band", "impact": "Contactgeluid: L'nT per band"}
CURVES_TITLE = {"airborne": "Gestandaardiseerd geluidsniveauverschil DnT",
                "impact": "Gestandaardiseerd contactgeluidsdrukniveau L'nT"}
BAND_TABLE_CAPTION = ("{name} per tertsband [dB]; banden dicht bij het achtergrondgeluiddrukniveau zijn "
                      "gearceerd")
COL_MEASUREMENT = "Meting"
COL_MEASUREMENT_IMPACT = "Meting (bronruimte \u2192 ontvangstruimte)"
COL_REQUIREMENT = "Eis ({basis})"
COL_CHECK = "Toetsing"
COL_REMARKS = "Opmerkingen"

CHECK_TEXT = {"none": "", "no_result": "geen resultaat", "complies": "Voldoet",
              "fails": "Voldoet niet", "inconclusive": "Niet conclusief"}
RT_TEXT = {"t30": "T30 (RT30)", "t20": "T20 (RT20)", "edt": "EDT"}

ROLE_TEXT = {"source": "Geluiddrukniveaus bronruimte", "receiver": "Geluiddrukniveaus ontvangstruimte",
             "tapping": "Contactgeluiddrukniveaus ontvangstruimte", "background": "Achtergrondgeluiddrukniveau",
             "rt": "Nagalmtijd"}
ROOM_LABEL = {"source": "Bronruimte", "tapping": "Bronruimte",
              "receiver": "Ontvangstruimte"}
ROOM_ROLE = {"receiver": "ontvangstruimte", "source": "bronruimte", "tapping": "bronruimte"}

EQUIP_HEAD = ("Instrument", "Serienummer", "Gebruikt voor")
FILES_TITLE = "Meetbestanden"
FILES_TITLE_DATES = "Meetbestanden (datum en tijd van de meting)"
PHOTO_UNREADABLE = "Foto kon niet worden gelezen: {name}"

# detail page
DETAIL_NO_RATING = "Beoordeling niet mogelijk (geen nagalmtijd bij {missing} Hz)"
DETAIL_SHIFT = ("Referentiecurve verschoven {shift} dB; som van de ongunstige afwijkingen "
                "{sum} dB (maximum 32,0 dB); T = {t}.")
DETAIL_REQUIREMENT = "Eis {basis} {requirement}"
DETAIL_CORRECTION = ("Correctie = correctie voor het achtergrondgeluiddrukniveau, toegepast op het geluiddrukniveau "
                     "in de ontvangstruimte.")
DETAIL_LIMIT = ("* Band minder dan 6 dB boven het achtergrondgeluiddrukniveau: gecorrigeerd met een vaste "
                "1,3 dB en slechts een grenswaarde (gearceerd).")
AIRBORNE_HEAD = ["Band\n[Hz]", "L1\n[dB]", "L2\ngemeten", "Lb\n[dB]", "L2\ngecorr.",
                 "Correc-\ntie [dB]", "T [s]", "D\n[dB]", "DnT\n[dB]", "Ref.-\ncurve",
                 "Ongunst.\nafw."]
IMPACT_HEAD = ["Band\n[Hz]", "Li\ngemeten", "Lb\n[dB]", "Li\ngecorr.", "Correc-\ntie [dB]",
               "T [s]", "L'nT\n[dB]", "Ref.-\ncurve", "Ongunst.\nafw."]


def summary_counts(n_air: int, n_imp: int) -> str:
    parts = ([f"{n_air} luchtgeluid"] if n_air else []) + ([f"{n_imp} contactgeluid"]
                                                           if n_imp else [])
    return f"{n_air + n_imp} {'meting' if n_air + n_imp == 1 else 'metingen'} ({', '.join(parts)})."


def count_metingen(n: int) -> str:
    return f"{n} {'meting' if n == 1 else 'metingen'}"


# ----------------------------------------------------------------------------- measurement names
_SUFFIX = re.compile(r" (#\d+)$")


def display_name(ev) -> str:
    """'luchtgeluid A naar B (muur)': the automatic name of a measurement in Dutch.

    Built from the parts (not by replacing words in the English name), so a room or comment
    that happens to contain ' to ' is left alone."""
    core = f"{KIND_WORD[ev.kind]} {ev.source_room} naar {ev.receiver_room}" if ev.source_room \
        else f"{KIND_WORD[ev.kind]} naar {ev.receiver_room}"
    if ev.comment.strip():
        core += f" ({ev.comment.strip()})"
    m = _SUFFIX.search(ev.name)
    return f"{core} {m.group(1)}" if m else core


# ----------------------------------------------------------------------------- notes and errors
# calc/building.py writes its per-measurement notes and errors in English (they also feed the
# viewer and the JSON). For the Dutch report they are translated here; a text that is not
# recognised is shown unchanged rather than dropped.
_NOTE_PATTERNS = [
    (re.compile(r"^no rating: reverberation time missing at (.*) Hz$"),
     r"geen beoordeling: nagalmtijd ontbreekt bij \1 Hz"),
    (re.compile(r"^(\d+) band\(s\) within 6 dB of background \(lower limit\)$"),
     r"\1 band(en) binnen 6 dB van het achtergrondgeluiddrukniveau (ondergrens)"),
    (re.compile(r"^(\d+) band\(s\) within 6 dB of background \(upper limit\)$"),
     r"\1 band(en) binnen 6 dB van het achtergrondgeluiddrukniveau (bovengrens)"),
    (re.compile(r"^averaged over several files$"), "gemiddeld over meerdere bestanden"),
    (re.compile(r"^file not found: (.*)$"), r"bestand niet gevonden: \1"),
    (re.compile(r"^receiving room '(.*)' does not exist$"), r"ontvangstruimte '\1' bestaat niet"),
    (re.compile(r"^source room '(.*)' does not exist$"), r"bronruimte '\1' bestaat niet"),
    (re.compile(r"^no source room level files$"), "geen bestanden met geluiddrukniveaus van de bronruimte"),
    (re.compile(r"^no receiving room level files$"),
     "geen bestanden met geluiddrukniveaus van de ontvangstruimte"),
    (re.compile(r"^no tapping machine level files$"),
     "geen bestanden met contactgeluiddrukniveaus van de ontvangstruimte"),
    (re.compile(r"^no reverberation time files for room '(.*)'$"),
     r"geen nagalmtijdbestanden voor ruimte '\1'"),
    (re.compile(r"^no background files \(building or room\)$"),
     "geen bestanden met het achtergrondgeluiddrukniveau (gebouw of ruimte)"),
]


def note_text(note: str) -> str:
    for pattern, replacement in _NOTE_PATTERNS:
        if pattern.match(note):
            return pattern.sub(replacement, note)
    return note
