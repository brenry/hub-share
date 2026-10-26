"""A picture is only its pixels: everything a file says about itself beyond them is cut out.

Applied once, where a file becomes a Temp picture (an engine's output landing, an upload taken in). The cut is
lossless when the file parses: PNG text, EXIF and time chunks go, and anything private; JPEG APP segments but
JFIF, the ICC profile and Adobe's colour marker, and comments, through every scan, and anything after the end
marker (a second picture, a phone's trailer); WebP EXIF and XMP chunks. A file that does not parse, or a photo
that leans on an orientation tag, is written again from its pixels (upright, JPEG at quality 95). Pixels,
transparency and colour management stay. Nothing is left as it was.
"""
from __future__ import annotations

import io
import os
import struct
from pathlib import Path

from PIL import Image, ImageOps

PNG_SIG = b"\x89PNG\r\n\x1a\n"
PNG_KEEP = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"iCCP", b"sBIT", b"bKGD",
            b"pHYs", b"acTL", b"fcTL", b"fdAT"}
JPEG_KEEP_APP = {0xE0, 0xE2, 0xEE}                    # JFIF, ICC_PROFILE, Adobe
WEBP_DROP = {b"EXIF", b"XMP "}
FORMATS = {"PNG": "PNG", "JPEG": "JPEG", "WEBP": "WEBP"}


def strip(path: Path) -> bool:
    """Rewrite `path` as its pixels alone. -> whether anything changed. Raises OSError/ValueError for a file that
    is not a picture Pillow can read."""
    data = path.read_bytes()
    out = _rewrite(data) if _leans(path) else _cut(data)
    if out is None:
        out = _rewrite(data)
    if out == data:
        return False
    tmp = path.with_name(f".{path.name}.clean")
    tmp.write_bytes(out)
    os.replace(tmp, path)
    return True


def _leans(path: Path) -> bool:
    """A photo whose EXIF orientation is not plain upright: its pixels must turn before the tag goes."""
    try:
        with Image.open(path) as im:
            return im.getexif().get(0x0112, 1) not in (None, 1)
    except (OSError, ValueError):
        return False


def _rewrite(data: bytes) -> bytes:
    """The picture again from its pixels, upright, in its own format, with nothing else in the file."""
    with Image.open(io.BytesIO(data)) as im:
        fmt = FORMATS.get(im.format or "", "PNG")
        im = ImageOps.exif_transpose(im) or im
        im.load()
        icc = im.info.get("icc_profile")
        out = io.BytesIO()
        extra = {"icc_profile": icc} if icc else {}
        if fmt == "JPEG":
            im.save(out, fmt, quality=95, subsampling=0, **extra)
        elif fmt == "WEBP":
            im.save(out, fmt, lossless=True, **extra)
        else:
            im.save(out, fmt, **extra)
    return out.getvalue()


def _cut(data: bytes) -> bytes | None:
    if data.startswith(PNG_SIG):
        return _png(data)
    if data.startswith(b"\xff\xd8"):
        return _jpeg(data)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return _webp(data)
    return None


def _png(data: bytes) -> bytes | None:
    out, pos = [PNG_SIG], len(PNG_SIG)
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        kind = data[pos + 4:pos + 8]
        end = pos + 12 + length
        if end > len(data):
            return None
        if kind in PNG_KEEP:
            out.append(data[pos:end])
        pos = end
        if kind == b"IEND":
            return b"".join(out)
    return None


def _scan_end(data: bytes, pos: int) -> int:
    """Past the entropy-coded data that starts at `pos`: the next marker that is not a stuffed byte or a restart."""
    while True:
        pos = data.find(b"\xff", pos)
        if pos < 0 or pos + 1 >= len(data):
            return len(data)
        marker = data[pos + 1]
        if marker != 0 and not 0xD0 <= marker <= 0xD7 and marker != 0xFF:
            return pos
        pos += 1 if marker == 0xFF else 2


def _jpeg(data: bytes) -> bytes | None:
    out, pos = [data[:2]], 2
    while pos + 2 <= len(data):
        if data[pos] != 0xFF:
            return None
        marker = data[pos + 1]
        if marker == 0xFF:                                  # fill byte
            pos += 1
            continue
        if marker == 0xD9:                                  # EOI: nothing after it is the picture
            out.append(b"\xff\xd9")
            return b"".join(out)
        if 0xD0 <= marker <= 0xD8 or marker == 0x01:        # standalone markers
            out.append(data[pos:pos + 2])
            pos += 2
            continue
        if pos + 4 > len(data):
            return None
        (length,) = struct.unpack(">H", data[pos + 2:pos + 4])
        end = pos + 2 + length
        if end > len(data):
            return None
        if marker == 0xDA:                                  # SOS: the scan's data follows, to the next marker
            end = _scan_end(data, end)
            out.append(data[pos:end])
            pos = end
            continue
        keep = not (0xE0 <= marker <= 0xEF and marker not in JPEG_KEEP_APP) and marker != 0xFE
        if marker == 0xE2 and not data[pos + 4:pos + 16].startswith(b"ICC_PROFILE\0"):
            keep = False
        if keep:
            out.append(data[pos:end])
        pos = end
    return None


def _webp(data: bytes) -> bytes | None:
    (riff,) = struct.unpack("<I", data[4:8])
    stop = min(len(data), 8 + riff)
    chunks, pos = [], 12
    while pos + 8 <= stop:
        kind = data[pos:pos + 4]
        (length,) = struct.unpack("<I", data[pos + 4:pos + 8])
        end = pos + 8 + length
        if end > stop:
            return None
        if kind not in WEBP_DROP:
            chunks.append(data[pos:end] + (b"\0" if length & 1 else b""))
        pos = end + (length & 1)
    if chunks and chunks[0][:4] == b"VP8X":
        flags = bytearray(chunks[0])
        flags[8] &= ~0x0C                                   # the EXIF and XMP bits are off: nothing follows
        chunks[0] = bytes(flags)
    body = b"".join(chunks)
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WEBP" + body
