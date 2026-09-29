# acoustics-viewer

Reads Svantek .SVL files and calculates airborne DnT,w (C; Ctr) and impact L'nT,w. Work in progress.

## Setup (Windows, PowerShell in the VS Code terminal)

    python -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    python -m pytest
    python run_airborne.py      # table in the terminal
    python run_impact.py        # impact sound L'nT,w in the terminal
    python -m gui               # the viewer: Building tab plus single airborne / impact tabs
    python -m gui --project my_building.json

On macOS/Linux: `source .venv/bin/activate` instead of the Activate line.

## Building tab

A building consists of rooms and measurements between them:

1. Choose the **building background** (used by every room without its own background) and the
   reverberation time to use (T30 by default).
2. Add **rooms** (source and receiving rooms). A room has a name, its reverberation time files
   (needed for receiving rooms) and optionally its own background. The room list is always kept
   in natural alphabetical order (`0.2.02` before `0.10.01`, numbers before letters).
3. Add **airborne** measurements (source room + receiving room + level files of both) and
   **impact** measurements (receiving room, optionally the tapping room + tapping level files).
   The reverberation time and background come from the receiving room / building.
   Measurements are named automatically: `<type> <source room> to <receiving room> (<comment>)`,
   e.g. `impact 0.2.03 Kitchen to B.1.02 Living (carpet)`. The optional comment gives context
   (floor covering, door open, position...). Two measurements with the same rooms need different
   comments. Project files from before this naming (schema 1) are converted when opened: a
   trailing `(...)` in the old name becomes the comment.

Each measurement can have a **requirement**: airborne (DnT,w, optionally + C or + Ctr) must be at
least the given value, impact (L'nT,w, optionally + C_I) at most the given value. Which quantity is
checked is chosen per building and measurement type ("Requirements are checked against"). Set it
in the measurement dialog, or for several selected measurements at once with "Set requirement...".
The Overview shows for each measurement whether it complies and by how many dB (margin), a summary
above the tabs counts them, and the bar charts mark the requirement with a black line. A failure is
reported as "not conclusive" when bands close to the background (which are only a limit value) could
have changed the result; a pass is always reliable, because those limit values can only make DnT
higher or L'nT lower than calculated.

The Overview tab compares all measurements in tables (DnT,w with C and Ctr; L'nT,w with C_I) and
bar charts; the other tabs overlay the DnT and L'nT curves and list the values per band. Untick
"Show" to leave a measurement out of the charts. A row that cannot be calculated (missing file,
room without reverberation time...) shows the reason and never stops the others. "Show details"
opens a measurement on the single-measurement tab. Projects are saved as `.json` files with
file paths relative to the project file, so a project folder can be moved or shared.
Keep real projects outside the code repository, or in a `projects/` folder, which is git-ignored:
they contain room names and measurement data of your clients.

## Several positions / decays

Every role (source room, receiving room, tapping machine, background, reverberation time)
accepts one or more files: Browse... replaces the selection, Add... appends, Clear empties it.
Level files of one role are energy-averaged per band, reverberation times of several decays
are averaged arithmetically per band. The program does not check the number of positions.

Impact results include the adaptation term C_I (100-2500 Hz): C_I = L_n,sum - 15 dB - L_n,w.

## Layout

    svl/      readers for the two SVL file types (levels, reverberation time)
    calc/     background correction, DnT / L'nT, ISO 717 ratings, airborne / impact / building models
    gui/      PySide6 + pyqtgraph viewer: building comparison, single airborne / impact pages
    tests/    pytest; samples/ holds the example files

The reference curves and C / Ctr spectra in calc/iso717.py were checked against
ISO 717-1 / 717-2 by the project owner. There is no independent end-to-end
reference result yet, so treat DnT,w values as unvalidated.

The SVL layout was reverse-engineered from a few sample files (Svantek SVAN 977);
see docs/svl-format.md for what is verified and what is not.

## Validation against the standards

`tests/test_iso717_examples.py` reproduces the worked examples of Annex C (ISO 717-1 Table C.1,
EN ISO 717-2:2021 Table C.1): ratings, shifted curves, deviations and adaptation terms all match,
with one exception that is understood: the C_I example for the bare floor (-10) was evidently summed
over 100-3150 Hz, whereas clause A.2.1 prescribes 100-2500 Hz, which this program follows (giving -11
for that example; see the comments in the test file). There is still no end-to-end reference result
for the SVL files themselves.

## Sample files

`samples/` is git-ignored on purpose (real measurements, serial numbers, and the
CSV exports contain local folder paths). Tests that need them are skipped when
they are missing. To run the full tests and `run_airborne.py`, put the sample
files (A_L2, B_L2, C_L20, B_L11, B_L4 as .SVL) into `samples/`. Four parser tests also
use L1.SVL, whose values were checked against SvanPC++; they are skipped without it.
