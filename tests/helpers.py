"""Test helpers: derive extra measurement files from the sample files."""
import numpy as np

from svl.parser import BLOCK_WORDS, DATA_START, N_BANDS, STORED_TOTAL_WORD, read_svl


def make_variant(src, dst, offset_db: float, only_bands=None):
    """Copy a level-type SVL file with every band and broadband level shifted by offset_db.

    only_bands: optional list of positions in the 45-band table (e.g. 36 = 3150 Hz); then only
    those bands are shifted and the broadband values stay as they are."""
    n_rec = read_svl(src).duration_s
    raw = bytearray(open(src, "rb").read())
    w = np.frombuffer(raw, dtype="<i2").copy()
    delta = int(round(offset_db * 100))
    for k in range(n_rec):
        body = DATA_START // 2 + k * BLOCK_WORDS + 13
        for j in range(3):
            start = body + j * (N_BANDS + 3)
            if only_bands is None:
                w[start:start + N_BANDS + 3] += delta
            else:
                for b in only_bands:
                    w[start + b] += delta
    if only_bands is None:
        w[STORED_TOTAL_WORD:STORED_TOTAL_WORD + N_BANDS + 3] += delta
    else:
        for b in only_bands:
            w[STORED_TOTAL_WORD + b] += delta
    open(dst, "wb").write(w.tobytes())
    return dst
