# Command line: `python -m calc`

Run from the project folder with the virtual environment active. Four commands:

| Command | Does |
|---|---|
| `airborne` | DnT,w (C; Ctr) from the level files of a source room and a receiving room, the background and the reverberation time of the receiving room |
| `impact` | L'nT,w (C_I) from tapping machine, background and reverberation time files of a receiving room |
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

`building PROJECT.json`: `--format`, `--output`, `--strict` (exit 1 if any measurement fails,
is not conclusive or could not be calculated), `--pdf FILE`, `--no-measurement-pages`,
`--no-band-tables`, `--no-photos`, `--no-dates`, `--date YYYY-MM-DD` (report date).

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
| `requirement.check` | `"complies"` \| `"fails"` \| `"inconclusive"` \| `"no_result"` | `inconclusive`: a failure that limit-value bands could change; a pass is always reliable |
| `requirement.margin_db` | int or null | positive = better than required |
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

### Building object (`building`)

| Key | Meaning |
|---|---|
| `schema_version`, `project`, `reverberation_time_used` | |
| `airborne_basis`, `impact_basis` | the quantities requirements are checked against |
| `summary` | counts: `complies`, `fails`, `inconclusive`, `no_result`, `none` (no requirement), `errors` |
| `equipment[]` | `{instrument, serial, used_for[]}` found in the files of all measurements |
| `measurements[]` | measurement objects as above (airborne first, then impact) |

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
