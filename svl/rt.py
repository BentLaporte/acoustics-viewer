"""Reverberation-time SVL files (SvanPC++ RT60 measurement, logger at 20 ms).

Reverse-engineered from a 977D file (L11.SVL) and verified value-for-value against the
SvanPC++ table "RT60 (SR)". The SV 977C files have the same contents with the framing described
in svl/parser.py (one word before and after each record, longer buffer header); a 977C file
("L34") agrees with its SvanPC++ table for every band and every total (tests/test_svanpc_977c.py).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from .parser import (N_BANDS, NOMINAL_HZ, Device, SvlError, band_frequencies, find_buffer,
                     find_preamble, read_device, read_measurement_time, read_octave_setup, MAGIC)

STEP_S = 0.02            # logger step, taken from the buffer header ("20")
REC_WORDS_EXTRA = 1      # flag word
RT60_BLOCK_ID = 27       # tag of the 'rt60 results' block


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
    device: Device | None = None
    measured_at: datetime | None = None

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

    try:
        device = read_device(raw)
        buf = find_buffer(raw)
        first, n_bands = read_octave_setup(raw)
    except SvlError as exc:
        raise SvlError(f"{path.name}: {exc}") from None
    band_hz = band_frequencies(first, n_bands)

    n_rec = buf.n_records
    rec_words = REC_WORDS_EXTRA + n_bands + 3
    # SV 977D: records follow each other; SV 977C: every record has one word in front and one
    # behind it and the buffer header states the record length (rec_words + 2)
    stride = rec_words if buf.header_words == 0x12 else buf.last_header_word
    frame = stride - rec_words
    if frame not in (0, 2):
        raise SvlError(f"{path.name}: this is not a reverberation time file of a known layout "
                       f"({stride} words per record, expected {rec_words} or {rec_words + 2})")
    allw = np.frombuffer(raw, dtype="<i2", count=len(raw) // 2)
    if buf.data_start // 2 + n_rec * stride > len(allw):
        raise SvlError(f"{path.name}: file too short for {n_rec} records")
    # 4 words in front of the first record if the measurement stopped before the buffer was
    # full (647 of 850 records), none if it was exactly full (400 of 400); checked on the data
    try:
        pre = find_preamble(allw, buf.data_start // 2, n_rec, stride, frame, buf.max_records)
    except SvlError as exc:
        raise SvlError(f"{path.name}: this does not look like a reverberation time file ({exc})") from None
    top = buf.data_start // 2 + pre
    end = top + n_rec * stride                           # first word behind the last record
    idx = (top + frame // 2 + stride * np.arange(n_rec)[:, None]
           + np.arange(rec_words)[None, :])
    w = allw[idx]
    levels = w[:, 1:1 + n_bands] / 100.0
    broadband = w[:, 1 + n_bands:] / 100.0

    # --- the stored RT60 results, behind the records ---------------------------------------
    # Block 27 ('rt60 results'): ..., 27, x, 80, then 45, 3, first band, last band, and one
    # 9-word row per band plus 3 rows for the totals A, C, Z. (A SV 977C file has another block
    # with 7-word rows in front of it; the id 27 tells them apart.)
    tail = allw[end:]
    hdr = None
    for i in range(3, len(tail) - 4):
        if (tail[i] == N_BANDS and tail[i + 1] == 3 and tail[i - 3] == RT60_BLOCK_ID
                and 0 <= tail[i + 2] < tail[i + 3] < N_BANDS):
            hdr = i
            break
    if hdr is None:
        raise SvlError(f"{path.name}: no RT60 result table found "
                       "(is this a reverberation time measurement?)")
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
                  t_edt, t_20, t_30, device, read_measurement_time(raw))
