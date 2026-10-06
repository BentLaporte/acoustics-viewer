"""The two instrument types, SV 977D and SV 977C (unit header, buffer layout, framing)."""
from pathlib import Path

import numpy as np
import pytest

from svl.parser import (BLOCK_WORDS, Device, SvlError, find_buffer, read_device, read_svl)



D_FILES = ["A_L2.SVL", "B_L2.SVL", "B_L4.SVL", "C_L20.SVL"]
C_FILE = "977C_example.SVL"
SAMPLES = Path(__file__).parent.parent / "samples"
needs_c = pytest.mark.skipif(not (SAMPLES / C_FILE).exists(), reason="977C sample missing")
needs_d = pytest.mark.skipif(not all((SAMPLES / n).exists() for n in D_FILES),
                             reason="977D samples missing")


def test_device_labels():
    assert Device(31, 977, 99942, 218).label == "SV 977D"
    assert Device(21, 977, 98053, 223).label == "SV 977C"
    assert Device(99, 977, 1, 100).label == "SV 977 (class 99)"          # unknown class: honest


@needs_d
@pytest.mark.parametrize("name, serial", [("A_L2.SVL", 99942), ("B_L2.SVL", 156226),
                                          ("B_L4.SVL", 156226), ("C_L20.SVL", 156226)])
def test_977d_files(name, serial):
    f = read_svl(SAMPLES / name)
    assert (f.device.label, f.device.class_code, f.device.firmware) == ("SV 977D", 31, 218)
    assert f.device.serial == serial and f.device.model == 977
    buf = find_buffer((SAMPLES / name).read_bytes())
    assert (buf.header_words, buf.data_start, buf.n_records) == (0x12, 0x5EC, 10)
    assert abs(f.leq_total() - f.stored_total).max() < 0.02


@needs_c
def test_977c_file_layout_and_content():
    raw = (SAMPLES / C_FILE).read_bytes()
    dev = read_device(raw)
    assert (dev.label, dev.class_code, dev.model, dev.firmware, dev.serial) == \
        ("SV 977C", 21, 977, 223, 98053)
    buf = find_buffer(raw)
    # longer buffer header (tag 0x130F), its last word is the record length: 157 + 2 framing words
    assert (buf.header_words, buf.data_start, buf.n_records, buf.last_header_word) == \
        (0x13, 0x5EE, 10, BLOCK_WORDS + 2)
    assert buf.size == len(raw) - buf.data_start
    # every record is framed by one word before and one after it (constant in this file)
    w = np.frombuffer(raw, dtype="<i2")
    first = buf.data_start // 2
    stride = buf.last_header_word
    prefix = {int(w[first + k * stride]) for k in range(10)}
    suffix = {int(w[first + k * stride + stride - 1]) for k in range(10)}
    assert len(prefix) == 1 and len(suffix) == 1
    f = read_svl(SAMPLES / C_FILE)
    assert f.name == "L1" and f.duration_s == 10 and f.device.label == "SV 977C"
    # the instrument's own stored whole-file spectrum agrees with our energy average
    assert f.stored_total is not None
    assert abs(f.leq_total() - f.stored_total).max() < 0.02
    assert f.laeq_total() == pytest.approx(f.stored_total_abc[0], abs=0.02)      # 94.91 dB
    # the same structure as the 977D: max >= Leq >= min in every second
    tot = lambda sp: 10 * np.log10(np.sum(10 ** (sp / 10)))                       # noqa: E731
    z = np.array([[tot(sp) for sp in sec.spectra] for sec in f.seconds])
    assert np.all((z[:, 0] >= z[:, 2]) & (z[:, 2] >= z[:, 1]))


@needs_c
def test_977c_stored_spectrum_sits_where_the_977d_one_does_relative_to_the_records():
    raw = (SAMPLES / C_FILE).read_bytes()
    buf = find_buffer(raw)
    w = np.frombuffer(raw, dtype="<i2")
    i = buf.data_start // 2 + 10 * buf.last_header_word + 124
    assert (int(w[i - 2]), int(w[i - 1])) == (12875, 257)             # same tag words as 977D


def test_unknown_layouts_give_clear_errors(tmp_path):
    junk = tmp_path / "junk.SVL"
    junk.write_bytes(b"SvanPC\x1a\x00" + bytes(3000))                 # right magic, no buffer
    with pytest.raises(SvlError, match="junk.SVL.*buffer header not found"):
        read_svl(junk)
    not_svl = tmp_path / "x.SVL"
    not_svl.write_bytes(b"hello" * 400)
    with pytest.raises(SvlError, match="bad magic"):
        read_svl(not_svl)


@needs_c
def test_truncated_977c_file_is_refused(tmp_path):
    raw = (SAMPLES / C_FILE).read_bytes()
    cut = tmp_path / "cut.SVL"
    cut.write_bytes(raw[:3000])                                        # size no longer matches
    with pytest.raises(SvlError):
        read_svl(cut)


# ------------------------------------------------------------------ framing words (977C)
def test_framing_words_encode_the_record_length():
    from svl.parser import FRAME_PREFIX, FRAME_SUFFIX, check_framing
    assert (FRAME_PREFIX | 159, FRAME_SUFFIX | 159) == (0xC69F, 0xCE9F)
    as_u16 = lambda v: v & 0xFFFF                                              # noqa: E731
    assert (as_u16(-14689), as_u16(-12641)) == (0xC69F, 0xCE9F)                # level file words
    assert (as_u16(-14811), as_u16(-12763)) == (0xC625, 0xCE25)                # RT file words
    stride = 5
    good = np.array([0xC605, 1, 2, 3, 0xCE05] * 4, dtype=np.uint16).view(np.int16)
    assert check_framing(good, 0, stride, 4)
    bad = good.copy()
    bad[10] = 7                                                                # damaged prefix
    assert not check_framing(bad, 0, stride, 4)
    assert not check_framing(good, 0, stride, 5)                               # runs past the end


@needs_c
def test_damaged_framing_is_refused(tmp_path):
    raw = bytearray((SAMPLES / C_FILE).read_bytes())
    buf = find_buffer(bytes(raw))
    at = buf.data_start + 2 * buf.last_header_word * 3                          # prefix of record 3
    raw[at:at + 2] = b"\x00\x00"
    broken = tmp_path / "broken.SVL"
    broken.write_bytes(bytes(raw))
    with pytest.raises(SvlError, match="not laid out as expected"):
        read_svl(broken)


@pytest.mark.skipif(not (SAMPLES / "977C_RT.SVL").exists(), reason="977C RT sample missing")
def test_damaged_framing_is_refused_in_rt_files(tmp_path):
    from svl.rt import read_rt
    raw = bytearray((SAMPLES / "977C_RT.SVL").read_bytes())
    buf = find_buffer(bytes(raw))
    at = buf.data_start + 8 + 2 * buf.last_header_word * 100 + 2 * (buf.last_header_word - 1)   # suffix of record 100
    raw[at:at + 2] = b"\x01\x00"
    broken = tmp_path / "broken_rt.SVL"
    broken.write_bytes(bytes(raw))
    with pytest.raises(SvlError, match="not laid out as expected"):
        read_rt(broken)
