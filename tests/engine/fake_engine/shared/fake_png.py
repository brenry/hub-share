"""The fake engine's pictures: a flat PNG of the task's size, with the task's settings as its `comment` text when the
engine's config keeps them in the file (`wgp.generate`)."""
from __future__ import annotations

import struct
import zlib


def write(path: str, width: int, height: int, comment: str | None) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    rows = (b"\x00" + b"\x40\x60\x80" * width) * height
    text = chunk(b"iTXt", b"comment\x00\x00\x00\x00\x00" + comment.encode("utf-8")) if comment else b""
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                + text + chunk(b"IDAT", zlib.compress(rows, 1)) + chunk(b"IEND", b""))
