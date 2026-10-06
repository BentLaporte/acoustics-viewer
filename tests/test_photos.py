"""Room photos: preparation for the report and thumbnails in the viewer."""
import io
import os

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from helpers import make_photo  # noqa: E402

from export.photos import MAX_SIDE, prepare_photo  # noqa: E402


def size_of(prepared):
    im = Image.open(io.BytesIO(prepared.data))
    return im.format, im.size


def test_large_photo_is_shrunk_and_reencoded(tmp_path):
    big = make_photo(tmp_path / "big.jpg", (4000, 3000))
    p = prepare_photo(big, "A caption")
    fmt, (w, h) = size_of(p)
    assert fmt == "JPEG" and max(w, h) == MAX_SIDE and (w, h) == (p.width, p.height)
    assert abs(w / h - 4 / 3) < 0.01                                   # aspect ratio kept
    assert p.caption == "A caption" and p.name == "big.jpg"
    assert len(p.data) < 200_000                                       # a plain picture stays small


def test_small_photo_is_not_enlarged(tmp_path):
    p = prepare_photo(make_photo(tmp_path / "s.jpg", (300, 200)))
    assert size_of(p)[1] == (300, 200)


@pytest.mark.parametrize("orientation, expected", [(1, (200, 100)), (6, (100, 200)),
                                                   (8, (100, 200)), (3, (200, 100))])
def test_phone_rotation_is_applied(tmp_path, orientation, expected):
    path = make_photo(tmp_path / f"o{orientation}.jpg", (200, 100), orientation=orientation)
    assert size_of(prepare_photo(path))[1] == expected


def test_png_with_transparency_and_palette(tmp_path):
    rgba = tmp_path / "a.png"
    Image.new("RGBA", (50, 50), (255, 0, 0, 0)).save(rgba)             # fully transparent
    p = prepare_photo(rgba)
    im = Image.open(io.BytesIO(p.data))
    assert im.mode == "RGB" and im.getpixel((10, 10))[0] > 240 and im.getpixel((10, 10))[1] > 240  # white
    pal = tmp_path / "p.gif"
    Image.new("P", (40, 30)).save(pal)
    assert prepare_photo(pal) is not None


def test_missing_and_broken_files_give_none(tmp_path):
    assert prepare_photo(tmp_path / "nope.jpg") is None
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"this is not a picture")
    assert prepare_photo(broken) is None
    empty = tmp_path / "empty.jpg"
    empty.write_bytes(b"")
    assert prepare_photo(empty) is None


def test_thumbnails(tmp_path):
    pytest.importorskip("PySide6")
    from PySide6 import QtCore, QtGui, QtWidgets
    from gui import thumbs
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    wide = make_photo(tmp_path / "w.jpg", (1600, 800))
    pix = thumbs.thumbnail(wide, QtCore.QSize(96, 72))
    assert pix is not None and pix.width() <= 96 and pix.height() <= 72
    assert abs(pix.width() / pix.height() - 2) < 0.1                   # aspect ratio kept
    portrait = make_photo(tmp_path / "p.jpg", (200, 100), orientation=6)   # phone: shown upright
    pp = thumbs.thumbnail(portrait, QtCore.QSize(96, 72))
    assert pp.height() > pp.width()
    assert thumbs.thumbnail(str(tmp_path / "missing.jpg")) is None
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"nope")
    assert thumbs.thumbnail(str(bad)) is None
    assert thumbs.thumbnail(wide, QtCore.QSize(96, 72)) is pix         # cached
    # a changed file is read again
    make_photo(tmp_path / "w.jpg", (100, 100))
    os.utime(tmp_path / "w.jpg", (1, 2_000_000_000))
    again = thumbs.thumbnail(wide, QtCore.QSize(96, 72))
    assert again is not pix and abs(again.width() - again.height()) <= 1
