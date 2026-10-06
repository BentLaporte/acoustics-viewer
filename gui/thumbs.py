"""Thumbnails of room photos for the viewer (cached, honours the camera's rotation)."""
from __future__ import annotations

import os

from PySide6 import QtCore, QtGui

IMAGE_FILTER = "Images (*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp);;All files (*)"
_cache: dict = {}


def thumbnail(path: str, size: QtCore.QSize = QtCore.QSize(96, 72)) -> QtGui.QPixmap | None:
    """A pixmap of at most `size`, or None when the file is missing or not a readable image."""
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        return None
    key = (path, stamp, size.width(), size.height())
    if key in _cache:
        return _cache[key]
    reader = QtGui.QImageReader(path)
    reader.setAutoTransform(True)                   # phone photos: apply the EXIF rotation
    original = reader.size()
    pix = None
    if original.isValid():
        # decode at reduced size: a 12 megapixel photo is then quick to load
        reader.setScaledSize(original.scaled(size * 2, QtCore.Qt.KeepAspectRatio))
        image = reader.read()
        if not image.isNull():
            pix = QtGui.QPixmap.fromImage(image).scaled(
                size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
    _cache[key] = pix
    return pix
