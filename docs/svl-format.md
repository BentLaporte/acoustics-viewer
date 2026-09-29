# SVL layout as decoded so far

Reverse-engineered from six files of a Svantek SVAN 977 (magic `SvanPC`), and
cross-checked against SvanPC++ CSV exports and pasted SvanPC++ result tables.
Nothing here comes from Svantek documentation. All words are little-endian
int16; levels are in units of 0.01 dB and can be negative.

## Common
- 0x22: measurement name (ASCII, space padded). Serial number near 0xE8.
- 0x26E: 1/x octave settings: `74, 12, 0x0101, 10, 3, first_index, n_bands`.
  `3` = 1/3 octave. Index counts tenths of a decade relative to 1 kHz:
  -31 -> 0.8 Hz, -17 -> 20 Hz. Seen: (-31, 45) and (-17, 31).
- Buffer header: tag 0x120F at 0x5C8 followed by mode, step, buffer size,
  number of records.

## Spectrum files (L1, A_L2, B_L2, C_L20): 45 bands, 1 record per second
Record of 157 words starting at 0x5EC: 1 flag word, 12 unidentified values,
then 3 x (45 band levels + 3 broadband values A, C, Z).
- The 3rd spectrum of each second is LZeq(1 s), verified (energy average over
  the file matches SvanPC++ 'Total results' within 0.05 dB, and the value the
  instrument stores itself within 0.008 dB).
- The 1st and 2nd spectra are probably max and min (totals ~103 dB and ~98 dB
  vs ~101 dB for LZeq in every second, in all files). NOT verified.
- Whole-file LZeq spectrum stored at word 2452 (45 bands + LAeq, LCeq, LZeq),
  preceded by the words 12875, 257.

## Reverberation time file (L11 / B_L11): 31 bands, 20 ms logger
647 records of 35 words (flag, 31 bands 20 Hz-20 kHz, 3 broadband A, C, Z),
starting 0x2C bytes after the buffer tag. Directly after the last record:
header `..., 45, 3, first, last` and 9-word rows (flag, EDT, RT20, RT30,
RTUser in ms, 4 unused; -1 = not available) for bands first..last of the
45-band table (18..38 = 50 Hz-5 kHz) followed by 3 rows for totals A, C, Z.
Verified value-for-value against the SvanPC++ table. SvanPC's RTResult equals
the RT30 column in the sample; what selects it is unknown.

## Not decoded
The 12 extra words per second, date/time in the binary header (the CSV export
shows them as text, format yy/mm/dd), calibration data, other instruments or
settings (other band counts, step times, profiles).
