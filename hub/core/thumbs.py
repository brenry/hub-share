"""Thumbnails live in memory, never on disk: a bounded, least-recently-used store of WebP bytes.

A thumbnail is made from a picture when it is first looked at and forgotten when the store is full, the file
changes, or the hub stops. Nothing about a picture exists anywhere but the picture.
"""
from __future__ import annotations

import io
import threading
from collections import OrderedDict

from PIL import Image, ImageOps

from hub.core.api import Invalid

CAP_MB = 256
MAX_PIXELS = 64_000_000


class ThumbStore:
    def __init__(self, cap_mb: int = CAP_MB) -> None:
        self._cap = cap_mb * 1024 * 1024
        self._size = 0
        self._items: OrderedDict[str, bytes] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> bytes | None:
        with self._lock:
            data = self._items.get(key)
            if data is not None:
                self._items.move_to_end(key)
            return data

    def put(self, key: str, data: bytes) -> None:
        with self._lock:
            old = self._items.pop(key, None)
            if old is not None:
                self._size -= len(old)
            self._items[key] = data
            self._size += len(data)
            while self._size > self._cap and self._items:
                _, gone = self._items.popitem(last=False)
                self._size -= len(gone)

    def forget(self, prefix: str) -> None:
        """Drop every thumbnail of one picture (keys start with its path)."""
        with self._lock:
            for key in [k for k in self._items if k.startswith(prefix)]:
                self._size -= len(self._items.pop(key))

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._size = 0

    def make(self, key: str, src: object, size: int, *, cover: bool = False) -> bytes:
        """The thumbnail under `key`, rendered from `src` (a path or bytes) when the store has none."""
        data = self.get(key)
        if data is None:
            data = render(src, size, cover=cover)
            self.put(key, data)
        return data


def render(src: object, size: int, *, cover: bool = False) -> bytes:
    """A WebP thumbnail of `src` (a path or bytes): at most `size` on the long edge, or a `size` square cut from
    the middle when `cover`. Raises Invalid for anything Pillow cannot read."""
    try:
        with Image.open(io.BytesIO(src) if isinstance(src, bytes) else src) as im:
            if im.width * im.height > MAX_PIXELS:
                raise Invalid("item", "Image is too large")
            im = ImageOps.exif_transpose(im)
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
            if cover:
                im = ImageOps.fit(im, (size, size), Image.Resampling.LANCZOS)
            else:
                im.thumbnail((size, size))
            out = io.BytesIO()
            im.save(out, "WEBP", quality=80)
            return out.getvalue()
    except Invalid:
        raise
    except Exception:
        raise Invalid("item", "That image could not be read") from None
