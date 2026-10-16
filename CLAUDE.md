# SVL Viewer – instructions for Claude Code

@AGENTS.md

The file above (AGENTS.md) holds the repository map, the commands and the hard rules. This file
adds the project background, the working agreements and the current status.

## Project in one paragraph

Python program that reads Svantek `.SVL` files (SV 977D and SV 977C), calculates building acoustic
ratings and shows them in a viewer: airborne DnT,w + C (ISO 717-1) and impact L'nT,w + CI
(ISO 717-2), for a whole building with several source and receiver rooms in one graph and one
table. It replaces old software that is no longer available, so there is **no reference result
to compare against yet**. Owner: Bent, acoustics engineer at SonIQ. Output goes to clients.

## How to work with Bent

* Conversation in **English**. Client-facing output (the PDF report) is in **Dutch**.
* Bent wants to grow as a programmer: **explain the code while you write it** (why, not only
  what). Short explanations next to the change, not a lecture.
* Strong eye for **user experience**: the design of the viewer matters, not only the numbers.
* **Acoustic correctness is checked against ISO 717-1 and ISO 717-2.** Flag any deviation from
  the standard explicitly, and say it when something is a choice rather than the standard.
* Bent likes **exact git commands** (add, commit, push) each time. Do not commit or push
  without being asked; propose the commit message and the commands.
* Add a test with every behaviour change and keep the suite green (`python -m pytest -q`).

## Settled decisions (do not revisit unless Bent asks)

* ISO 717 reference curves and C/Ctr spectra: checked by Bent, correct in the code.
* C_I energy sum uses 100-2500 Hz (ISO 717-2 clause A.2.1). Bent believes the bare-floor
  example in Annex C (result -10) is wrong; the Annex C numbers stay in the tests anyway.
* Extended frequency range terms: not needed for now.
* Report switches are one registry (`TOGGLES` in `export/report_options.py`), remembered per
  project (key `report_options`, schema stays 2). Requirements off removes everything about
  requirements everywhere. To add a switch: one `Toggle(...)`, one field in `ReportOptions`,
  use `options.<key>` in `pdf_report.py`.
* Installation noise (`calc/iso10052.py`, `calc/installation.py`): ISO 10052:2021 as used by
  NBN S 01-400-1:2022 4.4. LAeq,nT for stationary, LAFmax,nT for transient installations;
  LAFmax = profile 1 (A, Fast) of the 977, checked against SvanPC++. No background correction
  (ISO 10052 6.2.1), only the 6 dB check. Whole dB, halves up. Bent's choices: octave T =
  arithmetic mean of the three thirds; per band T30, else T20 (say so in output); the
  integrated (walking) method is allowed and marked as a deviation from 6.3.4. Our choice:
  background check of LAFmax against the background LAeq. ISO 16032 not available yet.
* Dutch wording lives only in `export/report_text.py`. Bent's terms: hamerklopmachine (tapping
  machine), bronruimte (source room, also for impact), ontvangstruimte (receiving room, also for
  impact), tertsband, achtergrondgeluiddrukniveau, geluiddrukniveaus.

## Sample files (not in the repo, never commit)

Real `.SVL` files live in `samples/` (git-ignored). Tests that need missing files skip. Names the
tests expect: `A_L1`, `A_L2`, `B_L2`, `B_L4`, `C_L20`, `B_L11`, `B_L15`, `977C_example`,
`977C_RT`, plus `L1.SVL`. All of them are present on this laptop (Windows). SvanPC++ reference
values are hard-coded in the tests, so no CSV files are needed.

## Status (15 Oct 2026)

All six roadmap steps exist: band spectra, rating curve with deviations, impact + C_I, averaging
over several files, whole-building comparison, Dutch PDF report with switches, command line.
Development moved from Cowork (Linux) to Claude Code on Windows; tests must pass on both, so
compare paths as `Path` objects, not strings. Last test run (Windows, `.venv` Python 3.13):
211 passed, 1 skipped (no sample band close to the background).

Open items, in rough order:

0. Installation noise (branch `installation-noise`): calculation and CLI done. Next: viewer
   page (time-window selection on the level history, note when T20 replaced T30), building
   comparison with requirements, Dutch report. The report needs a switch (`Toggle`) to show
   or hide the 'integrated method' remark. No transient sample yet (toilet flush, lift).
1. Excel export of the building comparison (reuse the switches registry).
2. End-to-end hand check of one real airborne and one real impact measurement against an
   independent calculation (Bent will do this later).
3. Viewer UX review with screenshots (samples are now available); the export dialog is about
   800 px tall, check it on the smallest laptop screen.
4. Bent to review the Dutch terms in the report; band headers "1,25k" / "3,15k" wrap onto two
   lines in the per-band table.
5. Optional: language switch (Dutch / English) for the report.
