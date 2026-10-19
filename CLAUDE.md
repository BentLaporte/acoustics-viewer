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
* Verdict = NBN S 01-400-1:2022 in-situ tolerance (5.4, 6.4, 8.4; `calc/nbn.py`): airborne and
  impact 2 dB, installation 1 dB; 4 / 3 dB for receiving rooms < 25 m3 that are not bedrooms;
  unknown volume = normal tolerance. A pass only thanks to the tolerance is its own status
  `tolerance` ("Voldoet binnen tolerantie", olive green). Project switch `nbn_tolerance`
  (default on); rooms carry `volume` and `bedroom`. Single-measurement CLI commands are strict.
  NBN S 01-400-3:2026 has the same numbers; the schools draft (-2) is not implemented.
* Measurement uncertainty ISO 12999-1:2020 (`calc/iso12999.py`): situation B, k = 1 (Bent's
  choice), U of the compared value, shown in the report (switch `uncertainty`), NOT used in the
  verdict (the NBN tolerance is the Belgian decision rule). None for installation noise.
* Report switch `measurement_remarks` (remarks column + per-page remarks). Off keeps what the
  standards require: limit values (ISO 16283 cl. 14) via the band tables, overestimated
  installation noise (ISO 10052 6.2.1) in its result box, and when those pages/tables are off
  too the notes name the measurements (`_remark_fallbacks` in `pdf_report.py`).
* Report switch `measurement_files` (the file list on measurement pages) is OFF by default
  (Bent: keeps a measurement on one page; no standard asks for file names). `file_dates` only
  applies with it (greyed out in the dialog). CLI: `--measurement-files` switches it on; a
  switch with default off gets a `--<name>` flag instead of `--no-<name>`.
* Measurement-page chart: no unshifted reference curve and no title (the rating is in the
  result box); axis ends on 5 dB, grid every 10 dB; ISO scale kept. Band table + caption are
  one KeepTogether. Checked on KPW (33 -> 26 pages, all on one page) and Centrimo (one bare
  floor with a 65 dB span still needs two pages: the table moves whole).
* Dutch wording lives only in `export/report_text.py`. Bent's terms: hamerklopmachine (tapping
  machine), bronruimte (source room, also for impact), ontvangstruimte (receiving room, also for
  impact), tertsband, achtergrondgeluiddrukniveau, geluiddrukniveaus.

## Sample files (not in the repo, never commit)

Real `.SVL` files live in `samples/` (git-ignored); `samples/README.md` lists them. Names are
`<type>_<role>_L<number>`: type = luchtgeluid, contactgeluid, installatiegeluid, ontvangstruimte
(shared by airborne and impact), parser or 977C; role = bron, ontvangst, BG (background), RT
(reverberation); L<number> = the original file number of the instrument. Tests that need missing
files skip. All of them are present on this laptop (Windows). SvanPC++ reference values are
hard-coded in the tests, so no CSV files are needed.

## Status (16 Oct 2026)

All six roadmap steps exist: band spectra, rating curve with deviations, impact + C_I, averaging
over several files, whole-building comparison, Dutch PDF report with switches, command line.
Installation noise (branch `installation-noise`) is in the calculation, CLI, building project,
viewer (dialog with level history: drag the time window; third overview section, hidden when
empty) and report (section, page per measurement, switch `integrated_method_note`). The report
title is now "Geluidsmetingen" (Bent's choice). Development moved from Cowork (Linux) to Claude
Code on Windows; tests must pass on both, so compare paths as `Path` objects, not strings.
Last test run (19 Oct 2026, Windows, `.venv` Python 3.13): 285 passed, 1 skipped.
Bent has the texts of NBN S 01-400-1:2022, NBN S 01-400-3:2026, the NBN S 01-400-2 draft (2012)
and ISO 12999-1/-2:2020. Open from NBN S 01-400-1 8.2 (not done, needs Bent): installation noise
may be background-corrected when it fails (max -2.2 dB, then an upper limit) and gets +5 dB for
a tonal character; our settled choice is no correction.

Parked by Bent: transient installations (no sample yet; LAFmax only checked on a stationary
file) and the engineering method ISO 16032.

Open items, in rough order:

00. Report per the standards' "expression of results" / "test report" clauses (Bent has the texts
   of ISO 717-1/-2:2020, ISO 16283-1:2014, ISO 16283-2:2020, ISO 10052:2021). Done: band values
   to 0,1 dB half up before rating (717 4.4 fn 1) and background correction thresholds on levels
   to 0,1 dB (16283 9.2: <= 6 dB limit, 6-10 formula, >= 10 none); first page names the
   standards with years, "veldmeting, ingenieursmethode" (controlemethode for 10052), "berekend
   uit tertsbandwaarden" (`METHOD` in report_text) and the test dates (also with file dates
   off); band charts at 5 mm per 1/3 octave and 20 mm per 10 dB (16283 cl. 12, `charts.band_figure`,
   shown at their own size; room photos sit under the legend so a measurement stays on one
   page); limit values as ">=45,3" / "<=45,3" on the detail page (comparison table: shading
   + caption, no room for the sign). To do (needs Bent): organisation name and client
   address; room volumes (nearest m3); construction / arrangement / impact source text;
   installation operating conditions and corner position (10052 cl. 8); uncertainty per
   ISO 12999-1 later (not available). Manual scanning (walking) is a standard method in
   ISO 16283 7.5, a deviation only for installation noise (10052 6.3.4).
0. Bent to review the installation noise Dutch wording (`report_text.py`: METHOD_TEXT,
   NOTE_INSTALLATION, note translations) and the viewer dialog.
1. Excel export of the building comparison (reuse the switches registry).
2. End-to-end hand check of one real airborne and one real impact measurement against an
   independent calculation (Bent will do this later).
3. Viewer UX review with screenshots (samples are now available); the export dialog is about
   800 px tall (one more switch now), check it on the smallest laptop screen. Screenshots:
   offscreen Qt needs `QT_QPA_FONTDIR=C:/Windows/Fonts`, otherwise all text is boxes.
4. Bent to review the Dutch terms in the report; band headers "1,25k" / "3,15k" wrap onto two
   lines in the per-band table.
5. Optional: language switch (Dutch / English) for the report.
