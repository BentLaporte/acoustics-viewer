"""Room photos for the report: rotate like the camera did, shrink, re-encode.

Phone photos are 3-8 MB each; put in a PDF as they are, a report would become huge. Every photo
is turned upright (EXIF orientation), shrunk to MAX_SIDE pixels and stored as JPEG.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

MAX_SIDE = 1400          # pixels, long side; enough for a 85 mm wide picture at 420 dpi
QUALITY = 82


@dataclass
class PreparedPhoto:
    data: bytes          # JPEG
    width: int           # pixels
    height: int
    caption: str = ""
    name: str = ""       # file name, for messages


def prepare_photo(path, caption: str = "") -> PreparedPhoto | None:
    """The photo ready for the PDF, or None if the file is missing or not a readable image."""
    from pathlib import Path
    try:
        from PIL import Image, ImageOps
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)            # upright, as seen on the camera
            if im.mode in ("RGBA", "LA", "P"):          # transparency -> white background
                im = im.convert("RGBA")
                flat = Image.new("RGB", im.size, "white")
                flat.paste(im, mask=im.split()[-1])
                im = flat
            else:
                im = im.convert("RGB")
            im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=QUALITY, optimize=True)
            return PreparedPhoto(buf.getvalue(), im.width, im.height, caption, Path(path).name)
    except Exception:                                   # missing, corrupt or unsupported (HEIC...)
        return None
