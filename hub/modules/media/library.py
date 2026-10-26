"""The Temp (`<data>/outputs`, ids `out/<day>/[<group>/]<file>`), the clips (`<data>/clips`, ids
`clips/<day>/[<group>/]<time>.mp4`, listed on their own page), the sounds (`<data>/sounds`, ids
`sounds/<day>/<time>.wav`, their own page) and the Drive's files (`drive/<folder>/<file>`).

Temp ids sort by time (day folder, then a time-stamped name), so paging is `before=<id>`. A folder between the
day and the file is the picture's group: the tree lists groups under Temp, and Favorites is one of them (a
favorite is a file moved into `<day>/Favorites/`). Nothing is kept about a picture but the picture. The clips root
pages the same way; a clip's size and length come from its boxes (`ctx.files.clip_facts`), never a thumbnail; the
sounds page the same way, a sound's length from its format (`ctx.files.sound_facts`).
Delete is core's (`ctx.files.delete`): the file and its thumbnails are erased at once, no trash.
"""
from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import quote

from PIL import Image

from hub.core.api import Ctx, Invalid

PREFIX = "out/"
IMAGES = (".png", ".jpg", ".jpeg", ".webp")
ROOTS = {"out": IMAGES, "clips": (".mp4",), "sounds": (".wav",)}       # a listed root and the files it holds
THUMB = 336
FAVORITES = "Favorites"


def outputs(ctx: Ctx) -> Path:
    return ctx.files.roots["out"]


def rel_of(item_id: Any, root: str = "out") -> str | None:
    """The path inside the root (Temp by default, or the clips or sounds) for a valid id of it, else None."""
    if not isinstance(item_id, str) or not item_id.startswith(f"{root}/"):
        return None
    rel = item_id[len(root) + 1:]
    parts = rel.split("/")
    if "\\" in rel or "\0" in rel or any(p in ("", ".", "..") or p.startswith(".") for p in parts):
        return None
    return rel if rel.lower().endswith(ROOTS[root]) else None


def is_clip(item_id: Any) -> bool:
    return rel_of(item_id, "clips") is not None


def is_sound(item_id: Any) -> bool:
    return rel_of(item_id, "sounds") is not None


def is_media(item_id: Any) -> bool:
    """A Temp, clips, sounds, Drive or Characters id."""
    return isinstance(item_id, str) and (rel_of(item_id) is not None or is_clip(item_id) or is_sound(item_id)
                                         or item_id.startswith(("drive/", "chars/")))


def group_of(item_id: str) -> str:
    """The folder(s) between the day and the file of a Temp or clips id, else ""."""
    rel = rel_of(item_id) or rel_of(item_id, "clips")
    parts = rel.split("/") if rel else []
    return "/".join(parts[1:-1]) if len(parts) > 2 else ""


def ids(root: Path, name: str = "out") -> list[str]:
    """Every id of a listed root (plain files only, no links), newest first."""
    found = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        base = Path(folder).relative_to(root).as_posix()
        for file in files:
            plain = file.lower().endswith(ROOTS[name]) and not file.startswith(".")
            if plain and not os.path.islink(os.path.join(folder, file)):
                found.append(f"{name}/" + (file if base == "." else f"{base}/{file}"))
    return sorted(found, reverse=True)


def describe_clip(ctx: Ctx, item_id: str) -> dict[str, Any] | None:
    """A clip as the screen shows it: its size and length from its boxes (None when they do not read), never a
    thumbnail its first frame (`clipthumb`)."""
    try:
        st = ctx.files.existing_media(item_id).stat()
    except (Invalid, OSError):
        return None
    facts = ctx.files.clip_facts(item_id) or {}
    return {"id": item_id, "kind": "clip", "url": ctx.files.url(item_id), "thumb": ctx.files.thumb_url(item_id),
            "w": facts.get("w"),
            "h": facts.get("h"), "seconds": facts.get("seconds"), "createdAt": st.st_mtime,
            "group": group_of(item_id), "fav": False}


def describe_sound(ctx: Ctx, item_id: str) -> dict[str, Any] | None:
    """A sound as the screen shows it: its length from its format (None when it does not read), no thumbnail."""
    try:
        st = ctx.files.existing_media(item_id).stat()
    except (Invalid, OSError):
        return None
    facts = ctx.files.sound_facts(item_id) or {}
    return {"id": item_id, "kind": "sound", "url": ctx.files.url(item_id), "thumb": None, "w": None, "h": None,
            "seconds": facts.get("seconds"), "createdAt": st.st_mtime, "group": "", "fav": False}


def describe(ctx: Ctx, item_id: str) -> dict[str, Any] | None:
    """One item for the screen, or None when the file is gone or unreadable. Only the size is read: the picture
    is all there is to know."""
    if is_clip(item_id):
        return describe_clip(ctx, item_id)
    if is_sound(item_id):
        return describe_sound(ctx, item_id)
    try:
        path = ctx.files.existing_image(item_id)
        st = path.stat()
        with Image.open(path) as im:
            width, height = im.size
    except (Invalid, OSError, ValueError):
        return None
    return {
        "id": item_id, "kind": "image", "url": ctx.files.url(item_id),
        "thumb": f"/thumbs/{quote(item_id, safe='/')}/{THUMB}?v={st.st_mtime_ns}", "w": width, "h": height,
        "createdAt": st.st_mtime, "group": group_of(item_id), "fav": group_of(item_id) == FAVORITES,
    }


def _made(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def page(ctx: Ctx, before: str | None, limit: int, root: str = "out") -> dict[str, Any]:
    """One page of the Temp (or the clips, or the sounds), every group in one stream, newest first; the screen shows
    one group at a time. `groups` counts each group's items (Temp always lists Favorites, so there is a place to
    drop onto)."""
    every = ids(ctx.files.roots[root], root)
    if root == "clips":                                  # newest first by the file's own time, whatever its name
        base = ctx.files.roots[root]
        every.sort(key=lambda i: _made(base / i.split("/", 1)[1]), reverse=True)
        at = every.index(before) + 1 if before in every else 0 if before is None else len(every)
        rest = iter(every[at:])
    else:
        rest = iter(i for i in every if before is None or i < before)
    items: list[dict[str, Any]] = []
    for item_id in rest:
        item = describe(ctx, item_id)
        if item is not None:
            items.append(item)
        if len(items) == limit:
            break
    counts = Counter(group_of(i) for i in every)
    if root == "out":
        counts.setdefault(FAVORITES, 0)
    groups = [{"name": g, "count": n} for g, n in sorted(counts.items(), key=lambda kv: kv[0].lower()) if g]
    return {"items": items, "more": any(True for _ in rest), "total": len(every), "groups": groups}
