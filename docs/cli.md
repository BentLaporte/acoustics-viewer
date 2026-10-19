# Command line: `python -m calc`

Run from the project folder with the virtual environment active. Five commands:

| Command | Does |
|---|---|
| `airborne` | DnT,w (C; Ctr) from the level files of a source room and a receiving room, the background and the reverberation time of the receiving room |
| `impact` | L'nT,w (C_I) from tapping machine, background and reverberation time files of a receiving room |
| `installation` | L_Aeq,nT or L_AFmax,nT of service equipment (installation noise, ISO 10052 / NBN S 01-400-1) from level files, reverberation time files and optionally a background file |
| `building` | evaluates every measurement of a building project file (`.json`); `--pdf` also writes the report |
| `info` | what an SVL file contains: instrument, serial, date and time, levels or reverberation times |

Output: `--format text` (default, for people), `--format json` (for programs, layout below),
`--format csv` (values per band; for `building` one row per measurement). `--output FILE` writes
to a file instead of the screen.

## Examples

```
python -m calc airborne --source A.L1.SVL --receiver B.L1.SVL --background C.L20.SVL --rt B.L15.SVL
python -m calc airborne ... --rt-kind t20 --requirement 54 --basis wc --format json
python -m calc impact --tapping B.L4.SVL --background C.L20.SVL --rt B.L11.SVL --requirement 58
python -m calc installation --level L22.SVL --rt L15.SVL L16.SVL --background L39.SVL --requirement 30
python -m calc installation --level L5.SVL@3-45 --rt L15.SVL --quantity lafmax --format json
python -m calc building "projects/My building/My building.json" --format csv --output results.csv
python -m calc building project.json --pdf report.pdf --no-dates --no-photos
python -m calc info A.L1.SVL B.L11.SVL --format json
```

Several files after one option are averaged: `--receiver B.L1.SVL B.L2.SVL B.L3.SVL`
(levels: energy average per band; reverberation times: arithmetic mean per band).

## Options

`airborne` and `impact`

| Option | Meaning |
|---|---|
| `--source`, `--receiver`, `--background`, `--rt` | airborne: level files of the source room and the receiving room, the background of the receiving room, its reverberation time file(s) |
| `--tapping`, `--background`, `--rt` | impact: tapping machine level file(s), background, reverberation time file(s) |
| `--rt-kind t30\|t20\|edt` | which reverberation time to use (default `t30`) |
| `--requirement DB` | required value in dB: airborne at least, impact at most |
| `--basis` | what the requirement is checked against. airborne: `w` = DnT,w (default), `wc` = DnT,w + C, `wctr` = DnT,w + Ctr. impact: `w` = L'nT,w (default), `wci` = L'nT,w + C_I |
| `--format`, `--output` | see above |
| `--strict` | exit status 1 if the requirement is not met or not conclusive |

`installation`

| Option | Meaning |
|---|---|
| `--level SVL[@START-END]` | level file(s) of the room. `@START-END` uses only those seconds (whole seconds, end exclusive; `@5-` = from second 5 to the end), e.g. one operating cycle |
| `--rt` | reverberation time file(s) of the room |
| `--background` | optional background level file(s): checked, never corrected |
| `--quantity laeq\|lafmax` | `laeq` = LAeq,nT, stationary installations (default); `lafmax` = LAFmax,nT, transient ones |
| `--method integrated\|positions` | `integrated` = moving microphone, any number of files, energy-averaged (default); `positions` = exactly three files, the corner position first, then two in the reverberant field (ISO 10052 6.3.4) |
| `--requirement DB` | maximum allowed value in dB |
| `--format`, `--output`, `--strict` | as above; `--format csv` gives one row per level file |

`building PROJECT.json`: `--format`, `--output`, `--strict` (exit 1 if any measurement fails,
is not conclusive or could not be calculated), `--pdf FILE`, `--no-measurement-pages`,
`--no-band-tables`, `--no-photos`, `--no-dates`, `--no-requirements`, `--no-term-c`,
`--no-term-ctr`, `--no-term-ci`, `--no-summary`, `--no-remarks`, `--no-equipment`,
`--no-notes` (each leaves that part out of the PDF; the choices saved in the project from the
viewer apply first, a flag only switches a part off), `--measurement-files` (the list of files
on each measurement page, off by default; `--no-dates` then leaves out their dates), `--date YYYY-MM-DD` (report date). The
PDF is in Dutch.

`info SVL...`: `--format text|json`, `--output`.

## Exit status and errors

| Status | Meaning |
|---|---|
| 0 | done |
| 1 | only with `--strict`: a requirement is not met or not conclusive, or a measurement could not be calculated |
| 2 | bad input: a file is missing or not a readable SVL file, or the project file is unreadable. Message on stderr, `error: ...` |

For `building` a measurement that cannot be calculated does not stop the others: it appears with
`"ok": false` and the reason in `"error"`.

## JSON layout (schema_version 1)

`airborne` and `impact` print one *measurement object*; `building` prints a *building object*
that contains a list of them. A complete example with fabricated numbers:
[`example-airborne.json`](example-airborne.json). Missing numbers are `null`, never NaN.
Names are not changed without raising `schema_version`.

### Measurement object

| Key | Type | Meaning |
|---|---|---|
| `schema_version` | int | 1 |
| `kind` | `"airborne"` \| `"impact"` | |
| `name` | string | `airborne <source> to <receiver> (<comment>)`; `airborne` / `impact` for a single calculation |
| `source_room` (airborne) or `tapping_room` (impact), `receiver_room`, `comment` | string | context (empty for single calculations) |
| `ok`, `error` | bool, string or null | `false` and the reason if it could not be calculated; the keys below are then empty |
| `remarks` | list of strings | e.g. bands close to the background, averaged files |
| `result.quantity` | `"DnT,w"` \| `"L'nT,w"` | |
| `result.single_number_db` | int or null | the rating, null if a band has no reverberation time |
| `result.C`, `result.Ctr` (airborne) / `result.CI` (impact) | int or null | spectrum adaptation terms |
| `result.reference_curve_shift_db` | int | shift of the ISO 717 reference curve |
| `result.unfavourable_deviation_sum_db` | number | at most `unfavourable_deviation_limit_db` (32.0) |
| `result.reverberation_time_used` | `"t30"` \| `"t20"` \| `"edt"` | |
| `result.bands_close_to_background` | int | bands within 6 dB of the background: limit values |
| `requirement` | object or null | only if a requirement was given |
| `requirement.compared_quantity` | string | e.g. `"DnT,w + C"` |
| `requirement.direction`, `value_db` | `">="` (airborne) \| `"<="` (impact), int | |
| `requirement.assessed_value_db` | int or null | the value that was compared |
| `requirement.check` | `"complies"` \| `"tolerance"` \| `"fails"` \| `"inconclusive"` \| `"no_result"` | `tolerance`: complies only within the in-situ tolerance of NBN S 01-400 (building only); `inconclusive`: a failure that limit-value bands could change; a pass is always reliable |
| `requirement.margin_db` | int or null | positive = better than required |
| `requirement.tolerance_db` | int | NBN S 01-400-1 5.4 / 6.4 / 8.4: 2 dB (installation 1 dB), 4 dB (3 dB) for receiving rooms under 25 m3 that are not bedrooms; 0 = strict (single-measurement commands, or switched off) |
| `uncertainty` | object or null | ISO 12999-1:2020 expanded uncertainty of the compared value; null without a rating |
| `uncertainty.expanded_db`, `coverage_factor`, `situation` | number, number, `"B"` | U = k u, situation B (in situ, Table 3 / Table 5), k = 1 |
| `files.<role>[]` | `{name, measured_at, instrument, serial}` | roles: `source`, `receiver`, `tapping`, `background`, `rt`; file names only; `measured_at` is ISO 8601 with two-second resolution |
| `bands_hz` | list of 16 ints | 100, 125, ..., 3150 |
| `bands.*` | list of 16 numbers | per band, same order as `bands_hz` |

`bands` for airborne: `source_level_db`, `receiver_level_measured_db`, `background_level_db`,
`receiver_level_corrected_db`, `background_correction` (`"ok"` \| `"corrected"` \| `"limit"`),
`reverberation_time_s`, `level_difference_D_db`, `standardized_level_difference_DnT_db`,
`reference_curve_unshifted_db`, `reference_curve_shifted_db`, `unfavourable_deviation_db`.
For impact: `tapping_level_measured_db`, `background_level_db`, `tapping_level_corrected_db`,
`background_correction`, `reverberation_time_s`, `standardized_impact_level_LnT_db`,
`reference_curve_unshifted_db`, `reference_curve_shifted_db`, `unfavourable_deviation_db`.

### Installation object (`installation`)

| Key | Meaning |
|---|---|
| `schema_version`, `kind` (`"installation"`), `ok`, `error`, `remarks` | as above; remarks name the integrated method, T20 used instead of T30, and a background check |
| `result.quantity` | `"LAeq,nT"` \| `"LAFmax,nT"` |
| `result.single_number_db` | int: the value as reported, whole dB (ISO 10052 7.3, halves rounded up) |
| `result.standardized_level_unrounded_db`, `measured_level_db`, `reverberation_index_k_db` | L_XY,nT before rounding, L_XY (energy average of the files), k |
| `result.method`, `method_text` | `"integrated"` \| `"positions"` |
| `result.background_level_laeq_db`, `background_affected` | background LAeq (null without a file); `true` if a file is less than 6 dB above it: the value is then overestimated, no correction is applied (ISO 10052 6.2.1) |
| `requirement` | as above with `direction` `"<="`; `inconclusive` = a failure while the level was within 6 dB of the background |
| `recordings[]` | `{file, start_s, end_s, duration_s, level_db, margin_to_background_db}` per level file |
| `reverberation.octave_s` | T in the octaves 500, 1000, 2000 Hz: arithmetic mean of the three one-third octaves in each (our choice) |
| `reverberation.third_octave_s`, `t20_instead_of_t30_hz` | T per one-third octave (mean over the files; T30, or T20 where T30 is missing) and the bands where T20 was used |
| `files.<role>[]` | roles `level`, `rt`, `background` |

Installation noise: `k = 10 lg((T500 + T1000 + T2000) / (3 x 0.5))`, `L_XY,nT = L_XY - k`, where
L_XY is the LAeq or the highest LAFmax (profile 1 of the instrument, A, Fast) of each file,
energy-averaged over the files.

### Building object (`building`)

| Key | Meaning |
|---|---|
| `schema_version`, `project`, `reverberation_time_used` | |
| `airborne_basis`, `impact_basis` | the quantities requirements are checked against |
| `nbn_tolerance` | true = requirements are checked with the NBN S 01-400 in-situ tolerance |
| `summary` | counts: `complies`, `tolerance`, `fails`, `inconclusive`, `no_result`, `none` (no requirement), `errors` |
| `equipment[]` | `{instrument, serial, used_for[]}` found in the files of all measurements |
| `measurements[]` | measurement objects as above (airborne first, then impact, then installation noise). An installation measurement is an *installation object* with, in addition, `name`, `source_room` (where the installation is, may be empty), `receiver_room` and `comment`; its `remarks` are the short ones of the viewer |

The building CSV has one row per measurement; the last column, `quantity`, says what
`single_number_db` is (`DnT,w`, `L'nT,w`, `LAeq,nT` or `LAFmax,nT`). In the project file installation
measurements are stored under `"installation"`, each level file with its time window
(`{"file", "start_s", "end_s"}`, `end_s` null = to the end of the file). Rooms carry
`volume_m3` (null = unknown) and `bedroom`; the project carries `nbn_tolerance` (missing = true).

### `info` output (JSON)

`file`, `kind` (`"level"` or `"reverberation"`), `instrument`, `serial`, `measured_at`,
`name_in_file`; level files: `duration_s`, `laeq_db`, `lzeq_db_by_band_hz`; reverberation files:
`records`, `step_s`, `t30_s_by_band_hz`, `t20_s_by_band_hz`, `edt_s_by_band_hz`.

## Reading the numbers

* Levels in dB, reverberation times in seconds, bands 100 to 3150 Hz (one-third octave).
* `DnT = D + 10 lg(T/0.5)`, `L'nT = Li - 10 lg(T/0.5)`; ratings by ISO 717-1 / 717-2.
* A band with `background_correction == "limit"` is within 6 dB of the background: corrected by a
  fixed 1.3 dB, so it is only a limit value (airborne: DnT can only be higher, impact: L'nT can
  only be lower than shown).
* Results are not validated end to end against an independent program (see the README).
