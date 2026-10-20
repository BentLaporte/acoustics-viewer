"""Test helpers: derive extra measurement files from the sample files."""
import numpy as np

from svl.parser import BLOCK_WORDS, N_BANDS, STORED_GAP, find_buffer, read_svl


def make_variant(src, dst, offset_db: float, only_bands=None):
    """Copy a level-type SVL file (977D or 977C) with every band and broadband level shifted
    by offset_db.

    only_bands: optional list of positions in the 45-band table (e.g. 36 = 3150 Hz); then only
    those bands are shifted and the broadband values stay as they are."""
    raw = open(src, "rb").read()
    buf = find_buffer(raw)
    stride = BLOCK_WORDS if buf.header_words == 0x12 else buf.last_header_word
    first = buf.data_start // 2 + (stride - BLOCK_WORDS) // 2     # skip the framing word
    w = np.frombuffer(raw, dtype="<i2").copy()
    delta = int(round(offset_db * 100))
    for k in range(buf.n_records):
        body = first + k * stride + 13
        for j in range(3):
            start = body + j * (N_BANDS + 3)
            if only_bands is None:
                w[start:start + N_BANDS + 3] += delta
            else:
                for b in only_bands:
                    w[start + b] += delta
    stored = buf.data_start // 2 + buf.n_records * stride + STORED_GAP
    if only_bands is None:
        w[stored:stored + N_BANDS + 3] += delta
    else:
        for b in only_bands:
            w[stored + b] += delta
    open(dst, "wb").write(w.tobytes())
    return dst


def make_photo(path, size=(800, 600), color=(90, 140, 200), orientation=None, fmt="JPEG"):
    """Write a plain coloured test picture (optionally with an EXIF orientation tag)."""
    from PIL import Image
    im = Image.new("RGB", size, color)
    kwargs = {}
    if orientation:
        ex = im.getexif()
        ex[0x0112] = orientation
        kwargs["exif"] = ex
    im.save(path, fmt, **kwargs)
    return str(path)


def make_flagged(src, dst, seconds):
    """Copy a level-type SVL file with the record flag set to 1 for the given (0-based) seconds,
    as the instrument does for seconds it marks (seen in real files; see svl.parser.Second)."""
    raw = open(src, "rb").read()
    buf = find_buffer(raw)
    stride = BLOCK_WORDS if buf.header_words == 0x12 else buf.last_header_word
    first = buf.data_start // 2 + (stride - BLOCK_WORDS) // 2     # skip the framing word
    w = np.frombuffer(raw, dtype="<i2").copy()
    for k in seconds:
        w[first + k * stride] = 1
    open(dst, "wb").write(w.tobytes())
    return dst
