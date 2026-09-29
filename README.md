# acoustics-viewer

Reads Svantek .SVL files and calculates DnT,w (C; Ctr). Work in progress.

## Setup (Windows, PowerShell in the VS Code terminal)

    python -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    python -m pytest
    python run_airborne.py

On macOS/Linux: `source .venv/bin/activate` instead of the Activate line.

## Layout

    svl/      readers for the two SVL file types (levels, reverberation time)
    calc/     background correction, DnT / L'nT, ISO 717 ratings
    tests/    pytest; samples/ holds the example files

The reference curves and C / Ctr spectra in calc/iso717.py were checked against
ISO 717-1 / 717-2 by the project owner. There is no independent end-to-end
reference result yet, so treat DnT,w values as unvalidated.

The SVL layout was reverse-engineered from a few sample files (Svantek SVAN 977);
see docs/svl-format.md for what is verified and what is not.

## Sample files

`samples/` is git-ignored on purpose (real measurements, serial numbers, and the
CSV exports contain local folder paths). Tests that need them are skipped when
they are missing. To run the full tests and `run_airborne.py`, put the sample
files (A_L2, B_L2, C_L20, B_L11, L1, L11 as .SVL, plus L11.csv) into `samples/`.
