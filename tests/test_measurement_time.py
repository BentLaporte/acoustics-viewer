"""Measurement date and time, and the buffer alignment (preamble)."""
import struct
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from svl.parser import (SvlError, find_buffer, find_preamble, read_measurement_time, read_svl)
from svl.rt import read_rt

SAMPLES = Path(__file__).parent.parent / "samples"


def have(*names):
    return pytest.mark.skipif(not all((SAMPLES / n).exists() for n in names),
                              reason="sample files missing")


# date and time as shown by SvanPC++: the header information of A.L1 and of the 977C file, and
# the "global settings" times of the CSV exports of the other 977D files
KNOWN = [("luchtgeluid_bron_L1.SVL", datetime(2026, 9, 22, 12, 6, 44)),      # SvanPC++ header information
         ("luchtgeluid_bron_L2.SVL", datetime(2026, 9, 22, 12, 11, 34)),     # CSV
         ("luchtgeluid_ontvangst_L2.SVL", datetime(2026, 9, 22, 12, 16, 18)),     # CSV
         ("ontvangstruimte_BG_L20.SVL", datetime(2026, 9, 28, 11, 40, 22))]    # CSV


@pytest.mark.parametrize("name, expected", KNOWN)
def test_977d_level_files_match_svanpc(name, expected):
    if not (SAMPLES / name).exists():
        pytest.skip("sample missing")
    assert read_svl(SAMPLES / name).measured_at == expected


@have("ontvangstruimte_RT_L11.SVL")
def test_977d_reverberation_file_matches_svanpc_csv():
    assert read_rt(SAMPLES / "ontvangstruimte_RT_L11.SVL").measured_at == datetime(2026, 9, 22, 12, 44, 2)


@have("977C_L1.SVL")
def test_977c_file_is_within_the_two_second_resolution():
    # SvanPC++ header information: 28/09/2026 11:08:35; the file stores seconds / 2 (floor)
    at = read_svl(SAMPLES / "977C_L1.SVL").measured_at
    assert at == datetime(2026, 9, 28, 11, 8, 34)
    assert 0 <= (datetime(2026, 9, 28, 11, 8, 35) - at).total_seconds() <= 1


@have("977C_RT_L34.SVL")
def test_977c_reverberation_file_has_a_plausible_date():
    at = read_rt(SAMPLES / "977C_RT_L34.SVL").measured_at
    assert at.year == 2026 and 1 <= at.month <= 12                   # no SvanPC++ value seen


@have("luchtgeluid_bron_L1.SVL")
def test_977d_header_information_of_a_l1():
    """SvanPC++ header information of A.L1.SVL: SV 977D, serial 99942, software 2.18.1."""
    d = read_svl(SAMPLES / "luchtgeluid_bron_L1.SVL").device
    assert (d.label, d.serial, d.firmware, d.model) == ("SV 977D", 99942, 218, 977)


def test_implausible_values_give_none(tmp_path):
    good = (SAMPLES / "luchtgeluid_bron_L2.SVL")
    if not good.exists():
        pytest.skip("sample missing")
    raw = bytearray(good.read_bytes())
    assert read_measurement_time(bytes(raw)) is not None
    raw[0xFA:0xFC] = struct.pack("<H", (26 << 9) | (13 << 5) | 5)      # month 13
    assert read_measurement_time(bytes(raw)) is None
    raw[0xFA:0xFC] = struct.pack("<H", (26 << 9) | (9 << 5) | 31)      # 31 September
    assert read_measurement_time(bytes(raw)) is None
    raw[0xFA:0xFC] = struct.pack("<H", (26 << 9) | (9 << 5) | 22)
    raw[0xFC:0xFE] = struct.pack("<H", 50000)                          # time of day > 24 h
    assert read_measurement_time(bytes(raw)) is None
    assert read_measurement_time(b"") is None
    assert read_measurement_time(bytes(raw[:0x40])) is None            # file ends before the block
    zeros = bytearray(raw)
    zeros[0x3C:0x40] = b"\x00\x00\x00\x00"                             # block walk hits length 0
    assert read_measurement_time(bytes(zeros)) is None


@have("luchtgeluid_bron_L2.SVL")
def test_seconds_have_two_second_resolution():
    raw = bytearray((SAMPLES / "luchtgeluid_bron_L2.SVL").read_bytes())
    tick = struct.unpack_from("<H", raw, 0xFC)[0]
    assert read_measurement_time(bytes(raw)).second % 2 == 0
    raw[0xFC:0xFE] = struct.pack("<H", tick + 1)
    assert read_measurement_time(bytes(raw)) == datetime(2026, 9, 22, 12, 11, 36)


# ------------------------------------------------------------------ preamble (buffer not full)
@have("ontvangstruimte_RT_L11.SVL", "parser_RT_volle_buffer_L15.SVL", "977C_RT_L34.SVL")
def test_preamble_follows_the_record_count():
    """4 words in front of the first record if the measurement stopped before the buffer was
    full (647 of 850, 380 of 400), none if it was exactly full (400 of 400)."""
    for name, n, mx, pre in (("ontvangstruimte_RT_L11.SVL", 647, 850, 4), ("parser_RT_volle_buffer_L15.SVL", 400, 400, 0),
                             ("977C_RT_L34.SVL", 380, 400, 4)):
        raw = (SAMPLES / name).read_bytes()
        buf = find_buffer(raw)
        assert (buf.n_records, buf.max_records) == (n, mx)
        stride = 35 if buf.header_words == 0x12 else buf.last_header_word
        frame = stride - 35
        w = np.frombuffer(raw, dtype="<i2")
        assert find_preamble(w, buf.data_start // 2, n, stride, frame, mx) == pre


@have("parser_RT_volle_buffer_L15.SVL")
def test_full_buffer_reverberation_file_reads_correctly():
    r = read_rt(SAMPLES / "parser_RT_volle_buffer_L15.SVL")
    assert r.levels.shape == (400, 31) and r.device.label == "SV 977D"
    assert r.levels.min() > -30 and r.levels.max() < 120                # aligned, not shifted
    z = r.broadband[:, 2]
    assert z[:20].min() > 90 and z.min() < 50                           # loud, then the decay
    assert r.measured_at == datetime(2026, 9, 22, 12, 50, 34)
    t30 = r.at([100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000,
                2500, 3150], "t30")
    assert not np.isnan(t30).any() and np.all((t30 > 0.2) & (t30 < 5))


def test_find_preamble_checks_the_data_and_refuses_unknown_layouts():
    # 977D style: the flag word (0) starts each 3-word record
    rec = [0, 7, 7]
    stride = 3
    full = np.array(rec * 4, dtype=np.int16)
    assert find_preamble(full, 0, 4, stride, 0, max_records=4) == 0           # full: no preamble
    early = np.array([9, 9, 9, 9] + rec * 4, dtype=np.int16)
    assert find_preamble(early, 0, 4, stride, 0, max_records=8) == 4          # stopped early
    # the header says 'early' but the data has no preamble: the data wins
    assert find_preamble(full, 0, 4, stride, 0, max_records=8) == 0
    # and the other way round
    assert find_preamble(early, 0, 4, stride, 0, max_records=4) == 4
    garbage = np.array([5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18], dtype=np.int16)
    with pytest.raises(SvlError, match="not laid out as expected"):
        find_preamble(garbage, 0, 4, stride, 0, max_records=4)
    # 977C style: framing words 0xC603 / 0xCE03 around 3-word records, record length 5
    pre, post = np.uint16(0xC600 | 5).view(np.int16), np.uint16(0xCE00 | 5).view(np.int16)
    framed = np.array([pre, 0, 1, 2, post] * 3, dtype=np.int16)
    assert find_preamble(framed, 0, 3, 5, 2, max_records=3) == 0
    shifted = np.concatenate([np.array([1, 2, 3, 4], dtype=np.int16), framed])
    assert find_preamble(shifted, 0, 3, 5, 2, max_records=9) == 4


@have("luchtgeluid_bron_L2.SVL", "luchtgeluid_ontvangst_L2.SVL", "ontvangstruimte_RT_L11.SVL", "ontvangstruimte_BG_L20.SVL")
def test_file_info_travels_with_the_results():
    from calc.airborne import compute_airborne
    res = compute_airborne(SAMPLES / "luchtgeluid_bron_L2.SVL", SAMPLES / "luchtgeluid_ontvangst_L2.SVL", SAMPLES / "ontvangstruimte_BG_L20.SVL",
                           [SAMPLES / "ontvangstruimte_RT_L11.SVL"])
    info = res.info
    assert set(info) == {"source", "receiver", "background", "rt"}
    assert [i.name for i in info["source"]] == ["luchtgeluid_bron_L2.SVL"] == res.names["source"]
    assert info["source"][0].measured_at == datetime(2026, 9, 22, 12, 11, 34)
    assert info["background"][0].measured_at == datetime(2026, 9, 28, 11, 40, 22)
    assert info["rt"][0].instrument == "SV 977D" and info["rt"][0].serial == 156226
    assert "/" not in info["source"][0].name and "\\" not in info["source"][0].name   # no folders
