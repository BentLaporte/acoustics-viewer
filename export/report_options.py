"""What the PDF report contains: the list of switches, their defaults and how they are stored.

To add a new switch later you only touch three places:

1. add a `Toggle(...)` to TOGGLES below (key, text for the dialog, default);
2. add a field with the same name to `ReportOptions` (a test checks that they match);
3. use `options.<key>` in export/pdf_report.py where the content is built.

The export dialog is generated from TOGGLES, and the chosen values are saved in the project file
(key "report_options"), so re-exporting a building gives the same report again. Unknown keys in
a project file are ignored and missing keys fall back to the default, so old project files and
newer versions of the program keep working together.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, fields


@dataclass(frozen=True)
class Toggle:
    key: str                  # name of the ReportOptions field and of the key in the project file
    label: str                # text of the checkbox in the export dialog
    group: str                # heading in the dialog; toggles of one group are shown together
    default: bool = True
    tip: str = ""             # tooltip


GROUPS = ("Results", "Sections", "Detail")

TOGGLES: tuple[Toggle, ...] = (
    Toggle("requirements", "Requirements and pass / fail", "Results",
           tip="Requirement column, 'Voldoet' / 'Voldoet niet', margins, requirement line in the "
               "charts and the wording about requirements in the summary and notes. When off, "
               "nothing about requirements appears anywhere in the report."),
    Toggle("term_c", "Adaptation term C (airborne)", "Results",
           tip="Always shown while requirements are on and a requirement is checked against "
               "DnT,w + C."),
    Toggle("term_ctr", "Adaptation term Ctr (airborne)", "Results",
           tip="Always shown while requirements are on and a requirement is checked against "
               "DnT,w + Ctr."),
    Toggle("term_ci", "Adaptation term C_I (impact)", "Results",
           tip="Always shown while requirements are on and a requirement is checked against "
               "L'nT,w + C_I."),
    Toggle("summary", "Summary sentence on the first page", "Sections"),
    Toggle("remarks", "Remarks (free text on the first page)", "Sections"),
    Toggle("equipment", "Equipment list", "Sections"),
    Toggle("notes", "Explanatory notes (Toelichting)", "Sections"),
    Toggle("room_photos", "Room photos", "Detail"),
    Toggle("per_measurement_pages", "One page per measurement (chart and values per band)",
           "Detail"),
    Toggle("per_band_tables", "Values per band under the comparison curves", "Detail"),
    Toggle("file_dates", "Date and time of each measurement file", "Detail"),
)


@dataclass
class ReportOptions:
    requirements: bool = True
    term_c: bool = True
    term_ctr: bool = True
    term_ci: bool = True
    summary: bool = True
    remarks: bool = True
    equipment: bool = True
    notes: bool = True
    room_photos: bool = True               # photos page and small photos on measurement pages
    per_measurement_pages: bool = True     # one page with chart and band table per measurement
    per_band_tables: bool = True           # values per band under the comparison curves
    file_dates: bool = True                # date and time of every measurement file
    date: dt.date | None = None            # report date, default today (not a switch)

    def to_dict(self) -> dict[str, bool]:
        """The switches only (what is saved in the project file)."""
        return {t.key: bool(getattr(self, t.key)) for t in TOGGLES}

    @classmethod
    def from_dict(cls, stored: dict | None, **extra) -> "ReportOptions":
        """Options from a saved dict: unknown keys and non-boolean values are ignored."""
        known = {t.key for t in TOGGLES}
        values = {k: v for k, v in (stored or {}).items() if k in known and isinstance(v, bool)}
        return cls(**values, **extra)


# the switches of the registry and the fields of ReportOptions must stay the same set
assert {t.key for t in TOGGLES} == {f.name for f in fields(ReportOptions)} - {"date"}
