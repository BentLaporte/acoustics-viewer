# SVL layout as decoded so far

Reverse-engineered from files of two Svantek instrument types, SV 977D and SV 977C (magic
`SvanPC`), and cross-checked against SvanPC++ CSV exports and pasted SvanPC++ result tables (977D
only, see below).
Nothing here comes from Svantek documentation. All words are little-endian
int16; levels are in units of 0.01 dB and can be negative.

## Instrument types

The unit header (tag 0x0E01 at 0x20, then block 0x0A02) holds, at word 15 after 0x20, a class
code, then the model (977 for both), the serial number (2 words) and a number that is probably
the firmware version:

| | class code | firmware | records |
|---|---|---|---|
| SV 977D | 31 | 218 | plain |
| SV 977C | 21 | 223 | framed, see below |

The letters C / D are not stored as text; both mappings are confirmed by the SvanPC++ header
information: the 977C file says "Device type: SVAN 977C, serial 98053, internal software version
2.23.1" (class code 21, firmware 223), the 977D file "Device type: SV 977D, serial 99942, internal
software version 2.18.1" (class code 31, firmware 218).

The reader recognises the layout from the buffer header (below), not from the class code. Found
by scanning for a word with low byte 0x0F whose data size matches the file:

| | buffer header tag | header words | data starts | per record |
|---|---|---|---|---|
| 977D | 0x120F | 18 | 0x5C8 + 36 = 0x5EC | 157 words |
| 977C | 0x130F | 19 | 0x5C8 + 38 = 0x5EE | 159 words |

The last word of the 977C buffer header is the record length (159). Each 977C record is the
977D record (157 words) with one word in front and one behind it. These framing words are
0xC600 + record length in front and 0xCE00 + record length behind (0xC69F and 0xCE9F for 159
words); the reader checks them for every record.
The stored whole-file spectrum sits 124 words behind the last record in both types, with the same
tag words (12875, 257) in front of it.

Verification status: 977D as described under 'Spectrum files'. 977C: one level file (10 s LZeq
of SvanPC++ against our energy average: max 0.007 dB; the instrument's own stored spectrum equals
the SvanPC++ values) and one reverberation file (every EDT, RT20, RT30 of the 21 bands and the
three totals equal SvanPC++). SvanPC++ itself refuses the CSV export of the 977C files with
"Unknown record length"; an Excel export of a window works.

## Measurement date and time
The block with id 0x04 ('global settings', at 0xF8) starts with a date word and a time word: date =
(year - 2000) << 9 | month << 5 | day, time = seconds since midnight / 2. Checked against SvanPC++
(header information or CSV) for seven files: six match to the second, the 977C file shows 11:08:35
in SvanPC++ and 11:08:34 here, because an odd second cannot be stored (two-second resolution).
This is the 'Measurement time / date' of the SvanPC++ header information. The unit header holds a
second stamp (same encoding, a few seconds earlier: the creation of the file).

## Buffer header, preamble
The buffer header also states the number of records the buffer can hold (word 7 and 8 after the
tag). If the measurement stopped before the buffer was full (647 of 850 records, 380 of 400) the
first record is preceded by 4 words (four values like 0xB0xx); if the buffer was exactly full
(400 of 400, and the 10 of 10 of the level files) there is no preamble. The reader takes the
expected value from the header and verifies it on the data (977D records start with a flag word 0,
977C records are framed), so a misalignment cannot go unnoticed.

## Record flag
The first word of a record is 0, or 1 for a second the instrument marked. Seen on loud
source-room seconds of a 977D (Himpe L1: seconds 1-6) and a 977C (KPW S_L10: seconds 4-5). The
SvanPC++ ASCII view of L1 shows the same words (as `0.01` = raw 1, every 157th word), so the
reading is right; what the mark means is not documented (probably overload, not verified).
When a 977D file has flags 1, the flags alone cannot confirm the alignment, so the reader also
requires the stored whole-file spectrum tag (12875, 257) in its place behind the last record and
at least one second with flag 0. Any other flag value is refused. Calculations leave the marked
seconds out (`SvlFile.usable`) and the remarks name them; the level history still shows them.

## Common
- 0x22: measurement name (ASCII, space padded). Serial number near 0xE8.
- 0x26E: 1/x octave settings: `74, 12, 0x0101, 10, 3, first_index, n_bands`.
  `3` = 1/3 octave. Index counts tenths of a decade relative to 1 kHz:
  -31 -> 0.8 Hz, -17 -> 20 Hz. Seen: (-31, 45) and (-17, 31).
- Buffer header: tag 0x120F at 0x5C8 followed by mode, step, buffer size,
  number of records.

## Spectrum files (L1, luchtgeluid_bron_L2, luchtgeluid_ontvangst_L2, ontvangstruimte_BG_L20): 45 bands, 1 record per second
Record of 157 words starting at 0x5EC: 1 flag word, 12 unidentified values,
then 3 x (45 band levels + 3 broadband values A, C, Z).
- The 3rd spectrum of each second is LZeq(1 s), verified (energy average over
  the file matches SvanPC++ 'Total results' within 0.05 dB, and the value the
  instrument stores itself within 0.008 dB).
- The 1st and 2nd spectra are Lmax and Lmin: the header says the logger holds 'Leq, Lmin, Lmax'
  and in every second of every file seen the totals are max >= Leq >= min. Not compared with
  SvanPC++ values (only the Leq is).
- Whole-file LZeq spectrum stored at word 2452 (45 bands + LAeq, LCeq, LZeq),
  preceded by the words 12875, 257.

## Reverberation time file (L11 / ontvangstruimte_RT_L11, 977C_RT_L34): 31 bands, 20 ms logger
The buffer starts with 4 words before the first record. Records of 35 words (flag, 31 bands
20 Hz-20 kHz, 3 broadband A, C, Z). On the 977D the records follow each other (the first one
at tag + 0x2C); on the 977C each record is 37 words: one word in front (0xC625 = -14811 in the
sample), the 35 words, one word behind (0xCE25 = -12763), and the buffer header states 37. The framing words are 0xC625 and 0xCE25, i.e. again 0xC600 / 0xCE00 plus the record length.
Directly after the last record, block 27 'rt60 results': `..., 27, x, 80, 45, 3, first, last`
and 9-word rows (flag, EDT, RT20, RT30, RTUser in ms, 4 unused; -1 = not available) for bands
first..last of the 45-band table (18..38 = 50 Hz-5 kHz) followed by 3 rows for totals A, C, Z.
Verified value-for-value against the SvanPC++ table, for a 977D file and for a 977C file.
SvanPC's RTResult equals the RT30 column in the 977D sample; what selects it is unknown.

The 977C file has one more block in front of block 27: id 116, same `45, 3, 18, 38` header and
24 rows of 7 words (five values around 240-310, then two values that look like levels x100, e.g.
7846 and 2224). Not decoded and not used; the reader finds block 27 by its id.

## Decoded but unused
The 12 words after the flag are, for the three profiles, [peak, max, min, eq] (header 'Logger
contents': LApeak/LAFmax/LAFmin/LAeq, LApeak/LASmax/LASmin/LAeq, LZpeak/LZFmax/LZFmin/LZeq for the
977C example). eq equals LAeq / LZeq of the Leq spectrum; the two A profiles share peak and eq.
max and min are detector values that can lag at sudden changes (a quiet second after a loud one
can show a high max).

Used and verified: the LAFmax of profile 1 (installation noise). For a 977D file
(installatiegeluid_L22, 10 s) the highest per-second max, the lowest per-second min and the
highest peak of profile 1 reproduce SvanPC++ "Main results" P1 (A, Fast): Lmax 46.1, Lmin 43.1,
Lpeak 60.1. The A total of the 1/3-octave Lmax spectra is *not* the LAFmax (47.1 dB there). The
reader checks that profile 1 is A-weighted (its eq equals the LAeq); Fast is assumed.

## Not decoded
Calibration data, other settings (other band counts, step times, profiles). A level file of a
measurement that was stopped early (fewer records than the buffer holds) has not been seen; the
reader would apply the 4-word preamble rule above and refuse the file if the data does not fit.
