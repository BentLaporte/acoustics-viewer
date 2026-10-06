# acoustics-viewer

Building acoustics from Svantek SVAN 977 sound level meter files (`.SVL`): airborne sound
insulation **DnT,w (C; Ctr)** and impact sound **L'nT,w (C_I)** per room, compared over a whole
building, checked against requirements and written to a PDF report. Work in progress.

* **Input:** `.SVL` files of the SV 977D and SV 977C (level measurements and reverberation time
  measurements), plus an optional building project file (`.json`).
* **Output:** numbers on the command line (text, JSON or CSV), a viewer (PySide6), a PDF report.
* **Status:** the reading of the files and the standard calculations are tested (see
  [Validation](#validation)); there is no independent end-to-end reference result for a complete
  field measurement yet, so treat results as unvalidated.

## Quick start

```
python -m venv .venv
.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m pytest                     # tests (those needing sample files are skipped without them)
```

Command line (details and the JSON layout: [docs/cli.md](docs/cli.md)):

```
python -m calc airborne --source A.SVL --receiver B.SVL --background BG.SVL --rt RT.SVL
python -m calc impact   --tapping T.SVL --background BG.SVL --rt RT.SVL --format json
python -m calc building my_building.json --pdf report.pdf
python -m calc info file.SVL
```

Viewer: `python -m gui` (or `python -m gui --project my_building.json`).

## What is calculated

For a pair of rooms (airborne) or one receiving room (impact), per one-third-octave band
100 to 3150 Hz, from the whole-file LZeq spectra (energy average over the file):

1. Background noise correction of the receiving room level: no correction if the signal is more than
   10 dB above the background, subtraction of the background between 6 and 10 dB, and a fixed
   1.3 dB (the band becomes a *limit value*) below 6 dB.
2. Standardized level difference `DnT = L1 - L2 + 10 lg(T/0.5)` (airborne) or standardized impact
   level `L'nT = Li - 10 lg(T/0.5)` (impact), with T the reverberation time (T30 by default; T20 or
   EDT can be chosen) of the receiving room.
3. Single-number rating by shifting the ISO 717 reference curve in 1 dB steps until the sum of the
   unfavourable deviations is at most 32.0 dB: DnT,w with the adaptation terms C and Ctr
   (ISO 717-1), L'nT,w with C_I over 100 to 2500 Hz (ISO 717-2).
4. Optionally a requirement: airborne must be at least, impact at most the required value,
   against DnT,w, DnT,w + C, DnT,w + Ctr (airborne) or L'nT,w, L'nT,w + C_I (impact).
   Result: `complies`, `fails`, `inconclusive` (a failure that bands close to the background could
   have changed) or `no_result`. A pass is always reliable.

Several files per role are averaged: levels as an energy average per band, reverberation times
as an arithmetic mean per band. The number of measurement positions is not checked.

## Repository map

| Path | What is in it |
|---|---|
| `svl/parser.py` | reader of level files: instrument, date and time, 3 spectra per second |
| `svl/rt.py` | reader of reverberation time files: level history and the stored RT60 table |
| `calc/levels.py`, `iso16283.py`, `iso717.py` | background correction, DnT / L'nT, ISO 717 ratings and adaptation terms |
| `calc/airborne.py`, `impact.py` | one airborne / impact calculation from files |
| `calc/building.py` | rooms, measurements, requirements, project file (`.json`), evaluation of a building |
| `calc/results.py` | results as plain dictionaries (the JSON of the command line) |
| `calc/cli.py` | the command line (`python -m calc`) |
| `export/` | PDF report (`pdf_report.py`), charts, room photos |
| `gui/` | the viewer (PySide6 + pyqtgraph) |
| `docs/cli.md` | command line reference and JSON layout; `docs/example-airborne.json` is an example |
| `docs/svl-format.md` | what is known about the SVL file layout and how well it is verified |
| `tests/` | pytest; `samples/` is for local sample files (git-ignored) |
| `AGENTS.md` | short guide for AI assistants and new contributors |

## Building projects (viewer and `python -m calc building`)

A building has **rooms** (name, reverberation time files, optional own background, photos) and
**measurements** between them: airborne (source room + receiving room + level files of both) and
impact (receiving room, optional tapping room, tapping level files). Background and reverberation
time come from the receiving room (or the building background). Measurements are named
automatically: `<type> <source room> to <receiving room> (<comment>)`, for example
`impact 0.2.03 Kitchen to B.1.02 Living (carpet)`; the optional comment gives context (floor
covering, door open, position...). Rooms are kept in natural order (`0.2.02` before `0.10.01`).
Projects are saved as `.json` with file paths relative to the project file, so a project folder
can be moved or shared. Details of the file: `calc/building.py` (`SCHEMA_VERSION`).

The viewer's Overview tab compares all measurements in tables and bar charts, the other tabs
overlay the DnT and L'nT curves; a measurement that cannot be calculated shows the reason and never
stops the others.

## Room photos

A room can have photos (first = main picture, optional captions). JPEG, PNG, BMP, TIFF and WebP
are supported (iPhone HEIC is not). In the PDF they are turned upright, shrunk (a 12 megapixel
photo becomes about 150 kB) and shown on a "Rooms" page and as small main pictures on the
measurement pages.

## PDF report

First page: building, client, location, author, remarks, results and compliance of all
measurements, notes and the **equipment** used (the instruments found in the files, with serial
numbers and what they measured, plus free text for other equipment). Then a comparison (bar
charts, DnT and L'nT curves with values per band) and optionally one page per measurement with
the rating chart, the values per band and the files that were used, each with the date and time
of its measurement (optional). File names only, never folder paths. Needs `reportlab`,
`matplotlib`, `Pillow` (in `requirements.txt`). Written by the viewer ("Export PDF...") or by
`python -m calc building PROJECT.json --pdf FILE`.

## Instruments

Level files and reverberation time files of both the **SV 977D** and the **SV 977C** are read
(also mixed in one building or one average). The layout is recognised from the file itself;
instrument type, serial number and software are in `.device`, the measurement date and time (two
second resolution) in `.measured_at`. See [docs/svl-format.md](docs/svl-format.md).

## Validation

* ISO 717: `tests/test_iso717_examples.py` reproduces the worked examples of Annex C (ISO 717-1
  Table C.1, EN ISO 717-2:2021 Table C.1), with one understood exception: the C_I example for the
  bare floor (-10) was summed over 100-3150 Hz, while clause A.2.1 prescribes 100-2500 Hz, which
  this program follows (-11 for that example).
* SVL files: the decoding was checked against SvanPC++ values (LZeq spectra, RT60 tables, header
  information, date and time) for both instrument types; see `tests/test_svanpc_977c.py`,
  `tests/test_parser.py`, `tests/test_rt.py`, `tests/test_measurement_time.py`.
* Not validated: a complete field measurement against an independent program's result.

## Privacy: what is not in this repository

Measurements, room photos, projects and reports belong to clients and are git-ignored
(`samples/*.SVL`, `projects/`, `*.pdf`, `*.xlsx`, `*.jpg`). Tests that need them are skipped when
they are missing. The files in `docs/` contain fabricated numbers only.
