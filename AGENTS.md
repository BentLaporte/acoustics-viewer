# Guide for AI assistants and new contributors

**What this is:** Python tools for building acoustics from Svantek SVAN 977 `.SVL` files: DnT,w
(airborne) and L'nT,w (impact) per ISO 717, a building comparison, a PDF report, a viewer.
Read `README.md` first (it has a repository map), then `docs/cli.md` and `docs/svl-format.md`.

## Run something

```
pip install -r requirements.txt
python -m pytest -q                                   # all tests; sample-dependent ones skip
python -m calc airborne --source S.SVL --receiver R.SVL --background B.SVL --rt T.SVL --format json
python -m calc info file.SVL --format json            # what is in a file
python -m calc building project.json --format json
```

JSON layout: `docs/cli.md`, example: `docs/example-airborne.json` (fabricated numbers; a test
checks that it matches the code). To regenerate it after changing the JSON:
`python -c "import json; from calc.examples import example_airborne as e; from calc.results import evaluated_to_dict as d; open('docs/example-airborne.json','w').write(json.dumps(d(e()), indent=2, ensure_ascii=False, allow_nan=False)+'\n')"`
Numbers in the JSON are plain floats/ints, `null` where a value is missing (never NaN).

## Where things are

* Standard calculations: `calc/levels.py`, `calc/iso16283.py`, `calc/iso717.py`,
  `calc/iso10052.py` (installation noise) (pure functions).
* File readers: `svl/parser.py` (level files), `svl/rt.py` (reverberation time files).
* Everything that combines files: `calc/airborne.py`, `calc/impact.py`, `calc/installation.py`,
  `calc/building.py`. The installation noise dialog of the viewer: `gui/installation_dialog.py`.
* Output: `calc/results.py` (JSON), `calc/cli.py` (command line), `export/pdf_report.py`, `gui/`.

## Rules that matter

1. **No client data in the repository.** Never commit `.SVL`, `.csv`, `.xlsx`, `.pdf`, photos or
   project files (`projects/`); `.gitignore` covers them. Examples and docs use fabricated numbers
   (`calc/examples.py`). Reports and JSON show file *names* only, never folder paths.
2. **The ISO 717 tables in `calc/iso717.py` were checked against the standards by the project
   owner. Do not change reference curves, adaptation spectra or the 32.0 dB rule.** The C_I sum
   range is 100-2500 Hz on purpose (see the comments in `tests/test_iso717_examples.py`).
3. **File layouts are reverse engineered.** `docs/svl-format.md` says what is verified against
   SvanPC++ and what is not. A reader must refuse a file it does not recognise (raise `SvlError`
   with a clear message) instead of guessing; alignment is checked on the data.
4. **Honest wording:** the report names the standards that were followed (as the standards require,
   e.g. ISO 16283-1 clause 14 a)); it never claims the software or the results are validated,
   certified or accredited. Every deviation from a named standard is stated in the report (e.g.
   the integrated method for installation noise, ISO 10052 6.3.4). Results are not validated end
   to end against an independent program.
5. A pass of a requirement is always reliable; a failure can be `inconclusive` when bands close to
   the background (limit values) could change it (`Evaluated.check` in `calc/building.py`).
6. Tests that compare with SvanPC++ values are in `tests/test_svanpc_977c.py`, `test_parser.py`,
   `test_rt.py`. Add a test with every behaviour change; keep the suite green.

## Conventions

English in code and UI, Dutch only in user data and in the PDF report (`export/report_text.py`
is the one place for its wording). Levels in dB, times in seconds, bands 100-3150 Hz
(16 bands). Measurements are named `<type> <source> to <receiver> (<comment>)`. Project files
carry `schema` 2 and use paths relative to the project file.
