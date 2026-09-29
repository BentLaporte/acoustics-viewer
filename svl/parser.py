"""Reader for Svantek .SVL files (SVAN 977 logger/spectrum files).

Reverse-engineered from a single sample (L1.SVL, 10 s, 1/3 octave, 1 s steps)
and cross-checked against the SvanPC++ "Total results" tab. Only the parts
listed below are decoded; everything else is ignored.

Verified against SvanPC++:
  * all values are uint16, little-endian, in units of 0.01 dB
  * 45 one-third-octave bands, 0.8 Hz ... 20 kHz (header: start index -31, 45 bands)
  * one buffer record per second; each record (157 words) is
        1 flag word, 12 words of unidentified values,
        3 x [45 band levels + 3 broadband values]
  * the 3rd spectrum of each second is LZeq(1 s); the energy average over
    all seconds reproduces SvanPC's 10 s LZeq to within 0.05 dB
  * the 3 broadband values after the LZeq spectrum are (LAeq, LCeq, LZeq)

NOT verified: what the 1st and 2nd spectrum are (their totals are ~103 dB and
~98 dB against ~100.7 dB for LZeq, so probably max and min), the 12 extra
words, and the header date/time. Other instruments or settings (other band
counts, other step times, other profiles) will need more work.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

MAGIC = b"SvanPC"
N_BANDS = 45
BLOCK_WORDS = 1 + 12 + 3 * (N_BANDS + 3)     # 157 words per second
DATA_START = 0x5EC                            # byte offset of first block (empirical)
BUFFER_TAG = 0x120F                           # "buffer header" tag, at 0x5C8 in the sample
LEQ_INDEX = 2                                 # which of the 3 spectra is LZeq

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


def read_octave_setup(raw: bytes) -> tuple[int, int]:
    """(first band index, number of bands) from the '1/x octave settings' block.

    Sits at byte 0x26E: tag 74, length 12, 0x0101, 10, 3 (=1/3 octave), first
    index, n bands. The first index counts in tenths of a decade relative to
    1 kHz (-31 -> 0.8 Hz, -17 -> 20 Hz). Verified on L1.SVL (-31, 45) and
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

    @property
    def leq_spectrum(self) -> np.ndarray:
        return self.spectra[LEQ_INDEX]

    @property
    def leq_broadband(self) -> np.ndarray:
        """(LAeq, LCeq, LZeq) of this second."""
        return self.broadband[LEQ_INDEX]


STORED_TOTAL_WORD = 2452       # word index of the stored whole-file LZeq spectrum
STORED_TAG = (12875, 257)      # the two words in front of it


@dataclass
class SvlFile:
    path: Path
    name: str
    serial: str
    seconds: list[Second] = field(default_factory=list)
    stored_total: np.ndarray | None = None      # 45 bands, LZeq over the whole file
    stored_total_abc: np.ndarray | None = None  # (LAeq, LCeq, LZeq) of the whole file

    @property
    def duration_s(self) -> int:
        return len(self.seconds)

    def leq_spectra(self) -> np.ndarray:
        """LZeq 1/3-octave spectra per second, shape (n_seconds, 45)."""
        return np.array([s.leq_spectrum for s in self.seconds])

    def leq_total(self) -> np.ndarray:
        """LZeq spectrum integrated over the whole file (energy average), 45 bands."""
        return energy_mean(self.leq_spectra())

    def laeq_total(self) -> float:
        """Broadband LAeq over the whole file."""
        a = np.array([s.leq_broadband[0] for s in self.seconds])
        return float(energy_mean(a))


def energy_mean(levels, axis=0):
    """Energy average of levels in dB."""
    levels = np.asarray(levels, float)
    return 10 * np.log10(np.mean(10 ** (levels / 10), axis=axis))


def read_svl(path) -> SvlFile:
    path = Path(path)
    raw = path.read_bytes()
    if raw[:6] != MAGIC:
        raise SvlError(f"{path.name}: not an SvanPC file (bad magic)")

    name = raw[0x22:0x2A].decode("ascii", "replace").strip()
    serial = raw[0xE8:0xF1].decode("ascii", "replace").strip()

    # buffer header: tag, 1, 0, size(u32), n_records(u32), n_records(u32), ...
    tag_pos = raw.find(struct.pack("<H", BUFFER_TAG), 0x280)
    if tag_pos < 0:
        raise SvlError(f"{path.name}: buffer header not found")
    _size, n_rec, n_rec2 = struct.unpack_from("<3I", raw, tag_pos + 6)
    if n_rec != n_rec2 or not (0 < n_rec < 100000):
        raise SvlError(f"{path.name}: implausible record count {n_rec}/{n_rec2}")

    need = DATA_START + n_rec * BLOCK_WORDS * 2
    if need > len(raw):
        raise SvlError(f"{path.name}: file too short for {n_rec} records")

    words = np.frombuffer(raw, dtype="<i2", count=n_rec * BLOCK_WORDS,
                          offset=DATA_START).astype(float) / 100.0
    f = SvlFile(path=path, name=name, serial=serial)
    for k in range(n_rec):
        blk = words[k * BLOCK_WORDS:(k + 1) * BLOCK_WORDS]
        extra = blk[1:13]
        body = blk[13:].reshape(3, N_BANDS + 3)
        spectra, bb = body[:, :N_BANDS], body[:, N_BANDS:]
        if not (np.all(np.abs(spectra) < 150) and np.all(np.abs(bb) < 150)):
            raise SvlError(f"{path.name}: record {k} does not match the expected layout")
        f.seconds.append(Second(spectra=spectra.copy(), broadband=bb.copy(),
                                extra=extra.copy()))
    # whole-file LZeq spectrum that the instrument stored itself (same place in all
    # four sample files; guarded by the two tag words in front of it)
    i = STORED_TOTAL_WORD
    allw = np.frombuffer(raw, dtype="<i2", count=len(raw) // 2)
    if (len(allw) > i + N_BANDS + 3 and tuple(allw[i - 2:i]) == STORED_TAG):
        f.stored_total = allw[i:i + N_BANDS] / 100.0
        f.stored_total_abc = allw[i + N_BANDS:i + N_BANDS + 3] / 100.0
    return f
