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
    value = round(float(value), nd) + 0.0      # + 0.0 turns -0.0 into 0.0: no minus zero
    return comma(f"{value:.{nd}f}").replace("-", "\u2212")


def date_text(d: dt.date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


# ----------------------------------------------------------------------------- fixed texts
TITLE = "Geluidsmetingen"
DOC_TITLE = "{name} - geluidsmetingen"          # PDF metadata
DOC_SUBJECT = "Geluidsmetingen"
EMPTY = "Er zijn nog geen metingen in dit gebouw."
PAGE_OF = "Pagina {page} van {total}"

FACT_CLIENT, FACT_LOCATION, FACT_AUTHOR = "Opdrachtgever", "Locatie", "Opgesteld door"
FACT_DATE = "Rapportdatum"
FACT_RT = "Gebruikte nagalmtijd"
FACT_TEST_DATE = "Datum van de metingen"
FACT_METHOD = "Meet- en beoordelingsmethode"
PERIOD_TO = "tot en met"

# The standards that were followed: the test report shall name them (ISO 16283-1/-2 clause 14,
# ISO 717 5.1 / 4.4, ISO 10052 clause 8), state that the result comes from a field measurement
# (engineering or survey method) and from one-third-octave band values (ISO 717-1 5.3, 717-2 4.4).
METHOD = {
    "airborne": "luchtgeluid: veldmeting volgens ISO 16283-1:2014 (ingenieursmethode), "
                "beoordeling volgens ISO 717-1:2020, berekend uit tertsbandwaarden",
    "impact": "contactgeluid: veldmeting met de hamerklopmachine volgens ISO 16283-2:2020 "
              "(ingenieursmethode), beoordeling volgens ISO 717-2:2020, berekend uit "
              "tertsbandwaarden",
    "installation": "installatiegeluid: veldmeting volgens ISO 10052:2021 (controlemethode), "
                    "beoordeling volgens NBN S 01-400-1:2022",
}
# installation noise with the integrated method: the deviation is stated with the standard ...
METHOD_INSTALLATION_DEVIATION = "; afwijking: ge\u00efntegreerde methode (zie toelichting)"
# ... or, when that remark is switched off, the standard is not claimed as the measurement method
METHOD_INSTALLATION_FORMULAS = ("installatiegeluid: berekend met de formules van ISO 10052:2021, "
                                "beoordeling volgens NBN S 01-400-1:2022")
LIMIT_PREFIX = {"airborne": "\u2265", "impact": "\u2264"}   # limit value: DnT >= ..., L'nT <= ...
DETAIL_EVALUATION = {
    "airborne": "Beoordeling volgens ISO 717-1:2020 op basis van tertsbandwaarden van een "
                "veldmeting volgens ISO 16283-1:2014 (ingenieursmethode).",
    "impact": "Beoordeling volgens ISO 717-2:2020 op basis van tertsbandwaarden van een "
              "veldmeting volgens ISO 16283-2:2020 (ingenieursmethode, hamerklopmachine).",
}
FACT_BASIS = "Eisen getoetst aan"
REMARKS = "Opmerkingen"
SECTION_AIRBORNE, SECTION_IMPACT = "Luchtgeluidisolatie", "Contactgeluiddrukniveau"
SECTION_INSTALLATION = "Installatiegeluid"
SECTION_COMPARISON = "Vergelijking"
SECTION_EQUIPMENT = "Apparatuur"
SECTION_NOTES = "Toelichting"
SECTION_ROOMS = "Ruimten"
ROOMS_INTRO = "Foto's van de ruimten waarop de metingen betrekking hebben."

KIND_WORD = {"airborne": "luchtgeluid", "impact": "contactgeluid",
             "installation": "installatiegeluid"}
KIND_TITLE = {"airborne": "Luchtgeluidisolatie", "impact": "Contactgeluiddrukniveau",
              "installation": "Installatiegeluid"}
KIND_AXIS = {"airborne": "hoger is beter", "impact": "lager is beter",
             "installation": "lager is beter"}
CURVES_HEAD = {"airborne": "Luchtgeluid: DnT per band", "impact": "Contactgeluid: L'nT per band"}
CURVES_TITLE = {"airborne": "Gestandaardiseerd geluidsniveauverschil DnT",
                "impact": "Gestandaardiseerd contactgeluidsdrukniveau L'nT"}
BAND_TABLE_CAPTION = "{name} per tertsband [dB]"
# added only when a band of the table is a limit value
BAND_TABLE_LIMITS = ("; banden dicht bij het achtergrondgeluiddrukniveau zijn gearceerd: dat zijn "
                     "grenswaarden ({name} {sign} de getoonde waarde)")
COL_MEASUREMENT = "Meting"
COL_MEASUREMENT_IMPACT = "Meting (bronruimte \u2192 ontvangstruimte)"
COL_REQUIREMENT = "Eis ({basis})"
COL_REQUIREMENT_PLAIN = "Eis"
COL_VALUE = "Waarde [dB]"
COL_QUANTITY = "Grootheid"
COL_CHECK = "Toetsing"
COL_REMARKS = "Opmerkingen"

CHECK_TEXT = {"none": "", "no_result": "geen resultaat", "complies": "Voldoet",
              "fails": "Voldoet niet", "inconclusive": "Niet conclusief"}
RT_TEXT = {"t30": "T30 (RT30)", "t20": "T20 (RT20)", "edt": "EDT"}

ROLE_TEXT = {"source": "Geluiddrukniveaus bronruimte", "receiver": "Geluiddrukniveaus ontvangstruimte",
             "tapping": "Contactgeluiddrukniveaus ontvangstruimte", "background": "Achtergrondgeluiddrukniveau",
             "rt": "Nagalmtijd", "level": "Geluiddrukniveaus installatiegeluid"}
ROOM_LABEL = {"source": "Bronruimte", "tapping": "Bronruimte",
              "receiver": "Ontvangstruimte"}

# installation noise (ISO 10052 as used by NBN S 01-400-1)
RT_INSTALLATION = "T30, T20 waar T30 ontbreekt (installatiegeluid)"
METHOD_TEXT = {"integrated": "Ge\u00efntegreerde methode: microfoon tijdens de meting door de "
                             "ruimte bewogen",
               "positions": "E\u00e9n meting nabij de hoek en twee metingen in het galmveld"}
INSTALL_LEVEL = {"laeq": "LAeq", "lafmax": "LAFmax"}
INSTALL_HEAD = ["Meetbestand", "Tijdvenster [s]", "Duur [s]", "{level}\n[dB]",
                "Boven achtergrond\n[dB]"]
INSTALL_WHOLE = "volledig ({end})"
INSTALL_RT_HEAD = ["Octaafband [Hz]", "Tertsbanden [Hz]", "T per tertsband [s]", "T octaaf [s]"]
DETAIL_INSTALL = ("Gemeten {level} = {measured} dB (energetisch gemiddelde van de metingen); "
                  "nagalmindex k = {k} dB; {quantity} = {measured} \u2212 {k} = {lnt} dB, "
                  "afgerond op 1 dB.")
DETAIL_INSTALL_BG = "Achtergrondgeluiddrukniveau LAeq = {bg} dB (alleen gecontroleerd, niet afgetrokken)."
DETAIL_INSTALL_RT = ("k = 10 lg((T500 + T1000 + T2000) / (3 \u00d7 0,5 s)); T per octaaf is het "
                     "rekenkundig gemiddelde van de drie tertsbanden (T30, of T20 waar T30 "
                     "ontbreekt).")
HISTORY_TITLE = "{file}: niveauverloop, het gebruikte tijdvenster is gearceerd"
NOTE_INSTALLATION = (
    "LAeq,nT en LAFmax,nT zijn het gestandaardiseerde equivalente en maximale installatiegeluid "
    "(lager is beter): het A-gewogen geluiddrukniveau, energetisch gemiddeld over de metingen, "
    "verminderd met de nagalmindex k = 10 lg((T500 + T1000 + T2000) / (3 \u00d7 0,5 s)), "
    "afgerond op 1 dB (formules van ISO 10052, zoals gebruikt in NBN S 01-400-1). LAFmax is "
    "het hoogste niveau met tijdweging Fast binnen het tijdvenster. Er wordt geen correctie "
    "voor het achtergrondgeluiddrukniveau toegepast; ligt het niveau minder dan 6 dB erboven, "
    "dan is de waarde overschat.")
NOTE_INTEGRATED = (
    "Ge\u00efntegreerde methode: in plaats van \u00e9\u00e9n meting nabij de hoek en twee "
    "metingen in het galmveld (ISO 10052, 6.3.4) is de microfoon tijdens de meting door de "
    "ruimte bewogen.")
NOTE_INSTALL_REQUIREMENT = ("Installatiegeluidresultaten moeten hoogstens gelijk zijn aan de "
                            "eis. De marge is het verschil in dB (positief = beter dan de eis).")
NOTE_INSTALL_INCONCLUSIVE = (
    "Niet conclusief (installatiegeluid): het geluiddrukniveau lag minder dan 6 dB boven het "
    "achtergrondgeluiddrukniveau. Het resultaat is daardoor mogelijk te hoog; of aan de eis "
    "voldaan is, kan niet met zekerheid worden vastgesteld.")
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
DETAIL_LIMIT = ("* Band 6 dB of minder boven het achtergrondgeluiddrukniveau: gecorrigeerd met een vaste "
                "1,3 dB en slechts een grenswaarde (gearceerd, weergegeven als DnT \u2265 \u2026 of "
                "L'nT \u2264 \u2026).")
AIRBORNE_HEAD = ["Band\n[Hz]", "L1\n[dB]", "L2\ngemeten", "Lb\n[dB]", "L2\ngecorr.",
                 "Correc-\ntie [dB]", "T [s]", "D\n[dB]", "DnT\n[dB]", "Ref.-\ncurve",
                 "Ongunst.\nafw."]
IMPACT_HEAD = ["Band\n[Hz]", "Li\ngemeten", "Lb\n[dB]", "Li\ngecorr.", "Correc-\ntie [dB]",
               "T [s]", "L'nT\n[dB]", "Ref.-\ncurve", "Ongunst.\nafw."]


def install_window(start: int, end, duration: int) -> str:
    """'5-35' or 'volledig (0-10)': the time window of one installation noise file in seconds."""
    if start == 0 and end is None:
        return INSTALL_WHOLE.format(end=f"0-{duration}")
    return f"{start}-{duration if end is None else end}"


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
    if ev.source_room:
        core = f"{KIND_WORD[ev.kind]} {ev.source_room} naar {ev.receiver_room}"
    else:                              # installation noise without source room: '... in <room>'
        core = f"{KIND_WORD[ev.kind]} {'in' if ev.kind == 'installation' else 'naar'} " \
               f"{ev.receiver_room}"
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
    # installation noise
    (re.compile(r"^integrated method \(moving microphone\)$"),
     "ge\u00efntegreerde methode (bewegende microfoon)"),
    (re.compile(r"^T20 used at (.*) Hz \(no T30\)$"), r"T20 gebruikt bij \1 Hz (geen T30)"),
    (re.compile(r"^background not checked$"), "achtergrondgeluiddrukniveau niet gecontroleerd"),
    (re.compile(r"^within 6 dB of background \(value overestimated\)$"),
     "minder dan 6 dB boven het achtergrondgeluiddrukniveau (waarde overschat)"),
    (re.compile(r"^room '(.*)' does not exist$"), r"ruimte '\1' bestaat niet"),
    (re.compile(r"^no installation noise level files$"),
     "geen bestanden met geluiddrukniveaus van het installatiegeluid"),
]


def note_text(note: str) -> str:
    for pattern, replacement in _NOTE_PATTERNS:
        if pattern.match(note):
            return pattern.sub(replacement, note)
    return note
