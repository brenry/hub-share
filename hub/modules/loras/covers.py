"""LoRA covers: a sidecar image beside the LoRA, else the embedded `modelspec.thumbnail`. None means the UI
draws initials. Thumbnails are made in memory (the hub's thumbnail store); nothing is written."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

from hub.core.api import Ctx, Invalid

from . import header
from .scan import Entry

SIZES = (96, 336)


def source(entry: Entry, embedded: bool) -> tuple[str, str] | None:
    """(kind, version) of the cover to draw: sidecar | embedded."""
    if entry.sidecar:
        try:
            return "sidecar", str(os.stat(entry.sidecar).st_mtime_ns)
        except OSError:
            pass
    return ("embedded", str(entry.mtime_ns)) if embedded else None


def url(entry: Entry, version: str) -> str:
    return f"/api/loras/thumb?id={quote(entry.id, safe='')}&v={quote(version, safe='')}"


def thumb(ctx: Ctx, entry: Entry, embedded: bool, size: int) -> bytes | None:
    """A square WebP thumbnail of the cover, from the store or made now."""
    found = source(entry, embedded)
    if found is None:
        return None
    kind, version = found
    key = f"{entry.path}|{kind}|{version}|{size}"
    data = ctx.files.thumbs.get(key)
    if data is not None:
        return data
    raw = Path(entry.sidecar).read_bytes() if kind == "sidecar" and entry.sidecar else header.thumbnail(entry.path)
    if raw is None:
        return None
    try:
        return ctx.files.thumbs.make(key, raw, size, cover=True)
    except Invalid:
        return None
