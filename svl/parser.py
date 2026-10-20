"""Reader for Svantek .SVL files (SVAN 977 logger/spectrum files).

Two instrument types are handled. Both are recognised from the data itself (the size of the
buffer header), the instrument type in the unit header is reported separately:

  * SV 977D (unit header class code 31, firmware 218 = software 2.18.1; the SvanPC++ header
    information says "Device type: SV 977D"): decoded from several files and cross-checked
    against the SvanPC++ "Total results" tab.
  * SV 977C (class code 21, firmware 223 = software 2.23.1; the SvanPC++ header information
    says "Device type: SVAN 977C"): the same record contents, but the buffer header is one word
    longer (tag 0x130F instead of 0x120F, its last word = record length 159) and every record is
    framed by one word before and one word after it (0xC600 / 0xCE00 + the record length).
    Decoded from one level file and one reverberation file; the level file agrees with the
    SvanPC++ 10 s LZeq to 0.007 dB and the reverberation table with SvanPC++ exactly (see
    tests/test_svanpc_977c.py).

Only the parts listed below are decoded; everything else is ignored.

Verified against SvanPC++:
  * all values are uint16, little-endian, in units of 0.01 dB
  * 45 one-third-octave bands, 0.8 Hz ... 20 kHz (header: start index -31, 45 bands)
  * one buffer record per second; each record (157 words) is
        1 flag word, 12 words of unidentified values,
        3 x [45 band levels + 3 broadband values]
  * the 3rd spectrum of each second is LZeq(1 s); the energy average over
    all seconds reproduces SvanPC's 10 s LZeq to within 0.05 dB
  * the 3 broadband values after the LZeq spectrum are (LAeq, LCeq, LZeq)

Content of a record, both types:
  * the logger holds the 1/3-octave Leq, Lmin and Lmax (header: "Octave 1/3 in logger"); in the
    file they come as [Lmax, Lmin, Leq]. The Leq is confirmed by SvanPC++; Lmax and Lmin follow
    from the header and from their levels (max >= Leq >= min in every second of every file seen)
    but have not been compared with SvanPC++ values.
  * the 12 words after the flag are, for the three profiles of the instrument, [peak, max, min,
    eq] (header: "Logger contents": LApeak/LAFmax/LAFmin/LAeq, LApeak/LASmax/LASmin/LAeq,
    LZpeak/LZFmax/LZFmin/LZeq). The eq values equal LAeq and LZeq of the Leq spectrum; the peak is
    the same in the two A-weighted profiles. The LAFmax of profile 1 is used for installation
    noise (SvlFile.lafmax) and verified against SvanPC++; the other values are not used.

Measurement date and time: see read_measurement_time (two-second resolution).

Not decoded: calibration data. Other settings (other band counts, step times, profiles) will
need more work.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

MAGIC = b"SvanPC"
N_BANDS = 45
BLOCK_WORDS = 1 + 12 + 3 * (N_BANDS + 3)     # 157 words per second
DATA_START = 0x5EC                            # byte offset of first block (empirical)
BUFFER_TAG = 0x120F                           # 977D "buffer header" tag, at 0x5C8
BUFFER_TAG_977C = 0x130F                      # 977C: one word longer
LEQ_INDEX = 2                                 # which of the 3 spectra is LZeq
STORED_GAP = 124                              # words between the last record and the stored total

# Instrument type, from the 'class code' in the unit header (word 15 after the file header).
# Both types report model 977; the class code is what differs (and the firmware). Both are
# confirmed by the SvanPC++ header information: a 977C file ("Device type SVAN 977C", serial
# 98053, software 2.23.1) has class code 21; a 977D file ("Device type SV 977D", serial 99942,
# software 2.18.1) has 31. The other 977D serial (156226) has 31 as well.
DEVICE_CLASS = {31: "SV 977D", 21: "SV 977C"}

# 1/3-octave centre frequencies, index n -> 10**(n/10) Hz*1e-3, n = -31 .. 13
BAND_INDICES = np.arange(-31, -31 + N_BANDS)
NOMINAL_HZ = np.array([
    0.8, 1, 1.25, 1.6, 2, 2.5, 3.15, 4, 5, 6.3, 8, 10, 12.5, 16, 20, 25, 31.5,
    40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000,
    1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500, 16000,
    20000])
assert len(NOMINAL_HZ) == N_BANDS

# 100 Hz ... 3150 Hz, the ISO 717 range
ISO_BANDS = NOMINAL_HZ[(NOMINAL_HZ >= 100) & (NOMINAL_HZ <= 3150)]
ISO_SLICE = slice(int(np.where(NOMINAL_HZ == 100)[0][0]),
                  int(np.where(NOMINAL_HZ == 3150)[0][0]) + 1)


class SvlError(ValueError):
    pass


@dataclass(frozen=True)
class Device:
    """The instrument that made the file, from the unit header."""
    class_code: int          # 31 on the SV 977D files, 21 on the SV 977C file
    model: int               # 977
    serial: int              # e.g. 99942
    firmware: int            # 218 / 223, probably firmware 2.18 / 2.23

    @property
    def label(self) -> str:
        return DEVICE_CLASS.get(self.class_code, f"SV {self.model} (class {self.class_code})")


def read_device(raw: bytes) -> Device:
    """Instrument type, serial number and firmware from the unit header (tag 0x0E01 at 0x20)."""
    if len(raw) < 0x50 or raw[:6] != MAGIC:
        raise SvlError("not an SvanPC file (bad magic)")
    w = struct.unpack_from("<10H", raw, 0x20 + 2 * 15)
    return Device(class_code=w[0], model=w[1], serial=w[2] + 65536 * w[3], firmware=w[4])


def read_measurement_time(raw: bytes) -> datetime | None:
    """Date and time of the measurement, from the 'global settings' block (id 0x04, 0xF8).

    The block starts with a date word (year-2000 in bits 9-15, month in bits 5-8, day in bits
    0-4) and a time word (seconds since midnight / 2). The two-second resolution means that an
    odd second is shown one second early (SvanPC++ 11:08:35, stored 11:08:34). This is the
    'Measurement date / time' of the SvanPC++ header information; the unit header holds a
    slightly earlier stamp (a few seconds before). None if the block or the values are not
    plausible.
    """
    pos = 0x20
    for _ in range(40):                              # walk the blocks: (length << 8) | id
        if pos + 8 > len(raw):
            return None
        head = struct.unpack_from("<H", raw, pos)[0]
        length, block_id = head >> 8, head & 0xFF
        if length == 0:
            return None
        if block_id == 0x04:
            date, tick = struct.unpack_from("<HH", raw, pos + 2)
            seconds = tick * 2
            try:
                return datetime(2000 + (date >> 9), (date >> 5) & 0xF, date & 0x1F,
                                seconds // 3600, seconds % 3600 // 60, seconds % 60)
            except ValueError:
                return None
        pos += 2 * length
    return None


@dataclass(frozen=True)
class BufferInfo:
    """Where the records are and how they are framed."""
    tag_pos: int             # byte offset of the buffer header
    header_words: int        # length of the buffer header in words (18 = 977D, 19 = 977C)
    data_start: int          # byte offset of the first record (frame included)
    size: int                # bytes of buffer data
    n_records: int
    last_header_word: int    # on the 977C: the record length in words (159)
    max_records: int = 0     # records the buffer can hold; fewer stored = measurement stopped early


FRAME_PREFIX, FRAME_SUFFIX = 0xC600, 0xCE00     # SV 977C framing words: marker + record length
PREAMBLE_WORDS = 4       # words in front of the first record when the buffer was not filled up
FLAGGED = 1              # record flag of a second marked by the instrument (see Second.flag)


def find_preamble(allw: np.ndarray, first: int, n_records: int, stride: int, frame: int,
                  max_records: int, confirm=None) -> int:
    """Words between the buffer header and the first record: 4 if the measurement stopped
    before the buffer was full (fewer records than the buffer holds), otherwise 0.

    The rule comes from the header, and is then checked on the data itself so that a
    misalignment can never go unnoticed: 977C records must be framed correctly, 977D records
    must start with a zero flag word. If the expected value does not pass, the other one is
    tried; if neither passes the layout is unknown and an SvlError is raised.

    A 977D record may carry flag 1 (a second marked by the instrument, see Second.flag). Such a
    flag weakens the zero-flag test, so then the alignment must also be confirmed by
    confirm(top): the instrument's stored whole-file spectrum at its fixed place."""
    expected = PREAMBLE_WORDS if n_records < max_records else 0
    for pre in (expected, PREAMBLE_WORDS - expected):
        top = first + pre
        if top + n_records * stride > len(allw):
            continue
        if frame:
            ok = check_framing(allw, top, stride, n_records)
        else:
            flags = allw[top + stride * np.arange(n_records)]
            ok = bool(np.all(flags == 0)) or bool(
                np.all((flags == 0) | (flags == FLAGGED)) and np.any(flags == 0)
                and confirm is not None and confirm(top))
        if ok:
            return pre
    raise SvlError("the records are not laid out as expected (unknown buffer layout)")


def check_framing(allw: np.ndarray, start: int, stride: int, n_records: int) -> bool:
    """True if every record starting at word `start` is framed as on the SV 977C: the word in
    front is 0xC6nn and the word behind it 0xCEnn, nn = the record length (e.g. 0xC69F, 0xCE9F
    for 159 words). A mismatch means the file is not laid out as assumed."""
    k = start + stride * np.arange(n_records)
    if k[-1] + stride > len(allw):
        return False
    pre, post = allw[k].astype(np.uint16), allw[k + stride - 1].astype(np.uint16)
    return bool(np.all(pre == FRAME_PREFIX | stride) and np.all(post == FRAME_SUFFIX | stride))


def find_buffer(raw: bytes) -> BufferInfo:
    """Locate the buffer header. A candidate must be consistent with the file: the data that
    follows the header has exactly the size the header states."""
    w = np.frombuffer(raw, dtype="<u2", count=len(raw) // 2)
    for pos in range(0x280 // 2, min(len(w) - 24, 0x900 // 2)):
        tag = int(w[pos])
        hdr = tag >> 8
        if tag & 0xFF != 0x0F or hdr not in (0x12, 0x13):
            continue
        size = int(w[pos + 3]) + 65536 * int(w[pos + 4])
        n_rec = int(w[pos + 5]) + 65536 * int(w[pos + 6])
        max_rec = int(w[pos + 7]) + 65536 * int(w[pos + 8])
        start = (pos + hdr) * 2
        if size == len(raw) - start and 0 < n_rec < 100000:
            return BufferInfo(pos * 2, hdr, start, size, n_rec, int(w[pos + hdr - 1]), max_rec)
    raise SvlError("buffer header not found (unknown file layout)")


def read_octave_setup(raw: bytes) -> tuple[int, int]:
    """(first band index, number of bands) from the '1/x octave settings' block.

    Sits at byte 0x26E: tag 74, length 12, 0x0101, 10, 3 (=1/3 octave), first
    index, n bands. The first index counts in tenths of a decade relative to
    1 kHz (-31 -> 0.8 Hz, -17 -> 20 Hz). Verified on luchtgeluid_bron_L1.SVL (-31, 45) and
    L11.SVL (-17, 31).
    """
    w = struct.unpack_from("<7h", raw, 0x26E)
    if w[0] != 74 or w[2] != 0x0101 or w[4] != 3:
        raise SvlError("1/3-octave settings block not found at 0x26E")
    return w[5], w[6]


def band_frequencies(first_index: int, n_bands: int) -> np.ndarray:
    """Nominal 1/3-octave centre frequencies for a band range."""
    i0 = first_index - (-31)          # position in the 45-band table
    if i0 < 0 or i0 + n_bands > N_BANDS:
        raise SvlError("band range outside the known 0.8 Hz - 20 kHz table")
    return NOMINAL_HZ[i0:i0 + n_bands]


@dataclass
class Second:
    """One 1-second buffer record."""
    spectra: np.ndarray            # shape (3, 45), dB
    broadband: np.ndarray          # shape (3, 3), dB, columns = A, C, Z weighting
    extra: np.ndarray              # 12 unidentified values, dB-scaled
    # first word of the record: 0, or 1 when the instrument marked the second. Seen on loud
    # source-room seconds of a 977D and a 977C; the meaning (probably overload) is not verified
    # against SvanPC++. Marked seconds hold doubtful values, so calculations leave them out
    # (SvlFile.usable); the level history still shows them.
    flag: int = 0

    @property
    def leq_spectrum(self) -> np.ndarray:
        return self.spectra[LEQ_INDEX]

    @property
    def lmax_spectrum(self) -> np.ndarray:
        """1/3-octave Lmax of this second (identified from the header and the levels, not
        compared with SvanPC++ values; the Leq spectrum is)."""
        return self.spectra[0]

    @property
    def lmin_spectrum(self) -> np.ndarray:
        return self.spectra[1]

    @property
    def profiles(self) -> np.ndarray:
        """Shape (3, 4): for the three profiles the logged values [peak, max, min, eq]. In the
        977C example the profiles are A fast, A slow and Z fast (LApeak/LAFmax/LAFmin/LAeq,
        LApeak/LASmax/LASmin/LAeq, LZpeak/LZFmax/LZFmin/LZeq). The eq column equals LAeq / LZeq of
        the Leq spectrum; max and min are detector values that can lag at sudden level changes."""
        return self.extra.reshape(3, 4)

    @property
    def leq_broadband(self) -> np.ndarray:
        """(LAeq, LCeq, LZeq) of this second."""
        return self.broadband[LEQ_INDEX]


STORED_TOTAL_WORD = 2452       # word index of the stored whole-file LZeq spectrum
STORED_TAG = (12875, 257)      # the two words in front of it
PROFILE_TOLERANCE_DB = 0.05    # profile 1 eq vs LAeq of the same second (seen: up to 0.01 dB)


@dataclass
class SvlFile:
    path: Path
    name: str
    serial: str
    device: Device | None = None
    measured_at: datetime | None = None
    seconds: list[Second] = field(default_factory=list)
    stored_total: np.ndarray | None = None      # 45 bands, LZeq over the whole file
    stored_total_abc: np.ndarray | None = None  # (LAeq, LCeq, LZeq) of the whole file

    @property
    def duration_s(self) -> int:
        return len(self.seconds)

    def leq_spectra(self) -> np.ndarray:
        """LZeq 1/3-octave spectra per second, shape (n_seconds, 45)."""
        return np.array([s.leq_spectrum for s in self.seconds])

    def leq_total(self, start: int = 0, end: int | None = None) -> np.ndarray:
        """LZeq spectrum integrated over a time window (default: the whole file; energy
        average), 45 bands; seconds marked by the instrument are left out."""
        return energy_mean(np.array([s.leq_spectrum for s in self.usable(start, end)]))

    @property
    def flagged_seconds(self) -> list[int]:
        """Seconds (0-based) marked by the instrument (Second.flag), left out of calculations."""
        return [k for k, s in enumerate(self.seconds) if s.flag]

    def usable(self, start: int = 0, end: int | None = None) -> list[Second]:
        """The seconds of a time window that calculations use: the window without the seconds
        the instrument marked. Raises SvlError if no second is left."""
        secs = [s for s in self.window(start, end) if not s.flag]
        if not secs:
            raise SvlError(f"{self.path.name}: every second of the measurement window is marked "
                           "by the instrument (record flag), so it cannot be used")
        return secs

    def laeq_total(self) -> float:
        """Broadband LAeq over the whole file."""
        return self.laeq()

    def window(self, start: int = 0, end: int | None = None) -> list[Second]:
        """The records of seconds start ... end (record k covers second k to k + 1, so end is
        exclusive). Whole seconds only: the logger stores one record per second."""
        end = self.duration_s if end is None else end
        if not (isinstance(start, (int, np.integer)) and isinstance(end, (int, np.integer))):
            raise ValueError("the time window is given in whole seconds")
        if not 0 <= start < end <= self.duration_s:
            raise ValueError(f"{self.path.name}: time window {start}-{end} s is outside the "
                             f"measurement (0-{self.duration_s} s)")
        return self.seconds[start:end]

    def laeq_per_second(self) -> np.ndarray:
        """LAeq of every second (the level history), dB."""
        return np.array([s.leq_broadband[0] for s in self.seconds])

    def lafmax_per_second(self) -> np.ndarray:
        """Highest LAF of every second (profile 1, see lafmax), dB. Not checked for the A
        weighting: for display; lafmax() checks it."""
        return np.array([s.profiles[0, 1] for s in self.seconds])

    def laeq(self, start: int = 0, end: int | None = None) -> float:
        """Broadband LAeq over a time window (default: the whole file)."""
        a = np.array([s.leq_broadband[0] for s in self.usable(start, end)])
        return float(energy_mean(a))

    def lafmax(self, start: int = 0, end: int | None = None) -> float:
        """Broadband LAFmax over a time window (default: the whole file): the highest of the
        per-second LAFmax values of profile 1.

        Verified against SvanPC++ "Main results" (installatiegeluid_L22: 46.1 dB). Not the A total
        of the 1/3-octave Lmax spectra, which gives a different, higher value (47.1 dB there).
        Profile 1 must be set to A weighting, Fast on the instrument (its default). The A
        weighting is checked on the data (its eq value equals the LAeq of every second); Fast
        cannot be read from the file and is assumed."""
        secs = self.usable(start, end)
        eq = np.array([s.profiles[0, 3] for s in secs])
        laeq = np.array([s.leq_broadband[0] for s in secs])
        if np.max(np.abs(eq - laeq)) > PROFILE_TOLERANCE_DB:
            raise SvlError(f"{self.path.name}: profile 1 is not A-weighted (its Leq differs from "
                           "the LAeq), so LAFmax cannot be read; set profile 1 to A, Fast")
        return float(np.max([s.profiles[0, 1] for s in secs]))


def energy_mean(levels, axis=0):
    """Energy average of levels in dB."""
    levels = np.asarray(levels, float)
    return 10 * np.log10(np.mean(10 ** (levels / 10), axis=axis))


def read_svl(path) -> SvlFile:
    """Read a level-type file (3 one-third-octave spectra per second) of an SV 977C or 977D."""
    path = Path(path)
    raw = path.read_bytes()
    if raw[:6] != MAGIC:
        raise SvlError(f"{path.name}: not an SvanPC file (bad magic)")

    name = raw[0x22:0x2A].decode("ascii", "replace").strip()
    serial = raw[0xE8:0xF1].decode("ascii", "replace").strip()
    try:
        device = read_device(raw)
        buf = find_buffer(raw)
    except SvlError as exc:
        raise SvlError(f"{path.name}: {exc}") from None

    # record length: the 977D has no framing, the 977C states 159 words in its header
    stride = BLOCK_WORDS if buf.header_words == 0x12 else buf.last_header_word
    frame = stride - BLOCK_WORDS                 # words around the record: 0 (977D) or 2 (977C)
    if frame not in (0, 2):
        raise SvlError(f"{path.name}: unknown record framing ({stride} words per record)")
    if buf.size < buf.n_records * stride * 2:
        raise SvlError(f"{path.name}: file too short for {buf.n_records} records")

    allw = np.frombuffer(raw, dtype="<i2", count=len(raw) // 2)

    def stored_total_in_place(top: int) -> bool:      # confirms the alignment, see find_preamble
        i = top + buf.n_records * stride + STORED_GAP
        return len(allw) > i + N_BANDS + 3 and tuple(allw[i - 2:i]) == STORED_TAG

    try:
        pre = find_preamble(allw, buf.data_start // 2, buf.n_records, stride, frame,
                            buf.max_records, stored_total_in_place)
    except SvlError as exc:
        raise SvlError(f"{path.name}: this does not look like a level file ({exc})") from None
    first = buf.data_start // 2 + pre
    f = SvlFile(path=path, name=name, serial=serial, device=device,
                measured_at=read_measurement_time(raw))
    for k in range(buf.n_records):
        at = first + k * stride + frame // 2     # skip the word in front of the record
        blk = allw[at:at + BLOCK_WORDS].astype(float) / 100.0
        extra = blk[1:13]
        body = blk[13:].reshape(3, N_BANDS + 3)
        spectra, bb = body[:, :N_BANDS], body[:, N_BANDS:]
        if not (np.all(np.abs(spectra) < 150) and np.all(np.abs(bb) < 150)):
            raise SvlError(f"{path.name}: record {k} does not match the expected layout")
        flag = int(allw[at])
        if flag not in (0, FLAGGED):
            raise SvlError(f"{path.name}: record {k} has an unknown flag ({flag})")
        f.seconds.append(Second(spectra=spectra.copy(), broadband=bb.copy(),
                                extra=extra.copy(), flag=flag))
    # whole-file LZeq spectrum that the instrument stored itself, a fixed distance behind the
    # last record; guarded by the two tag words in front of it
    i = first + buf.n_records * stride + STORED_GAP
    if len(allw) > i + N_BANDS + 3 and tuple(allw[i - 2:i]) == STORED_TAG:
        f.stored_total = allw[i:i + N_BANDS] / 100.0
        f.stored_total_abc = allw[i + N_BANDS:i + N_BANDS + 3] / 100.0
    return f
