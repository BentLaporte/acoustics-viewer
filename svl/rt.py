"""Reverberation-time SVL files (SvanPC++ RT60 measurement, logger at 20 ms).

Reverse-engineered from L11.SVL and verified value-for-value against the
SvanPC++ table "RT60 (SR)":

  * 647 records of 35 words: 1 flag word, 31 band levels (20 Hz - 20 kHz),
    3 broadband levels (A, C, Z). Levels are signed int16, unit 0.01 dB.
  * directly after the last record: a header (..., 45, 3, first, last) and a
    table of 9-word rows, one per band from `first` to `last` (indices in the
    45-band table, 18..38 = 50 Hz..5 kHz), followed by 3 rows for the
    broadband totals A, C, Z.  Row = flag, EDT, RT20, RT30, RTUser (ms),
    then 4 unused words.  -1 means "not available" (SvanPC shows ***).
  * SvanPC's "RTResult" equals the RT30 column in every row of the sample.
    RTUser is not set in the sample, so what selects the result column is
    unconfirmed; RtFile.result() therefore takes the kind explicitly.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .parser import (BUFFER_TAG, N_BANDS, NOMINAL_HZ, SvlError, band_frequencies,
                     read_octave_setup, MAGIC)

STEP_S = 0.02            # logger step, taken from the buffer header ("20")
REC_WORDS_EXTRA = 1      # flag word


@dataclass
class RtFile:
    path: Path
    name: str
    band_hz: np.ndarray       # bands of the level history (20 Hz - 20 kHz)
    levels: np.ndarray        # (n_records, n_bands) dB
    broadband: np.ndarray     # (n_records, 3) dB, A, C, Z
    rt_hz: np.ndarray         # bands of the stored RT table
    edt: np.ndarray           # seconds, NaN where unavailable
    t20: np.ndarray
    t30: np.ndarray
    total_edt: np.ndarray     # (A, C, Z)
    total_t20: np.ndarray
    total_t30: np.ndarray

    def result(self, kind: str = "t30") -> np.ndarray:
        """Stored reverberation time per band (rt_hz), kind = 'edt' | 't20' | 't30'."""
        try:
            return {"edt": self.edt, "t20": self.t20, "t30": self.t30}[kind.lower()]
        except KeyError:
            raise ValueError("kind must be 'edt', 't20' or 't30'") from None

    def at(self, freqs, kind: str = "t30") -> np.ndarray:
        """Reverberation time at the given band centre frequencies (NaN if absent)."""
        table = dict(zip(self.rt_hz.tolist(), self.result(kind).tolist()))
        return np.array([table.get(float(f), np.nan) for f in freqs])

    @property
    def time_s(self) -> np.ndarray:
        return np.arange(len(self.levels)) * STEP_S


def _ms_to_s(x: np.ndarray) -> np.ndarray:
    x = x.astype(float)
    x[x < 0] = np.nan
    return x / 1000.0


def read_rt(path) -> RtFile:
    path = Path(path)
    raw = path.read_bytes()
    if raw[:6] != MAGIC:
        raise SvlError(f"{path.name}: not an SvanPC file (bad magic)")
    name = raw[0x22:0x2A].decode("ascii", "replace").strip()

    first, n_bands = read_octave_setup(raw)
    band_hz = band_frequencies(first, n_bands)

    tag = raw.find(struct.pack("<H", BUFFER_TAG), 0x280)
    if tag < 0:
        raise SvlError(f"{path.name}: buffer header not found")
    _mode, _step, _size, n_rec, _max = struct.unpack_from("<HHIII", raw, tag + 2)
    rec_words = REC_WORDS_EXTRA + n_bands + 3
    # the first record starts 0x2C bytes after the tag (empirical, same in the sample)
    start = tag + 0x2C
    end = start + n_rec * rec_words * 2
    if end > len(raw):
        raise SvlError(f"{path.name}: file too short for {n_rec} records")

    w = np.frombuffer(raw, dtype="<i2", count=n_rec * rec_words,
                      offset=start).reshape(n_rec, rec_words)
    levels = w[:, 1:1 + n_bands] / 100.0
    broadband = w[:, 1 + n_bands:] / 100.0

    # --- stored RT60 table, directly behind the records ---------------------
    tail = np.frombuffer(raw, dtype="<i2", offset=end, count=(len(raw) - end) // 2)
    hdr = None
    for i in range(min(40, len(tail) - 4)):
        if tail[i] == N_BANDS and tail[i + 1] == 3 and 0 <= tail[i + 2] < tail[i + 3] < N_BANDS:
            hdr = i
            break
    if hdr is None:
        raise SvlError(f"{path.name}: no RT60 result table found")
    lo, hi = int(tail[hdr + 2]), int(tail[hdr + 3])
    n_rows = (hi - lo + 1) + 3
    rows_at = hdr + 4
    if rows_at + 9 * n_rows > len(tail):
        raise SvlError(f"{path.name}: RT60 table truncated")
    rows = tail[rows_at:rows_at + 9 * n_rows].reshape(n_rows, 9)
    if not np.all(rows[:, 0] == 1):
        raise SvlError(f"{path.name}: unexpected RT60 row layout")

    rt_hz = NOMINAL_HZ[lo:hi + 1]
    nb = hi - lo + 1
    edt, t20, t30 = (_ms_to_s(rows[:nb, c]) for c in (1, 2, 3))
    t_edt, t_20, t_30 = (_ms_to_s(rows[nb:, c]) for c in (1, 2, 3))
    return RtFile(path, name, band_hz, levels, broadband, rt_hz, edt, t20, t30,
                  t_edt, t_20, t_30)
