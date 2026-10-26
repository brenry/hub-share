"""What the First cut has made, as pointers only: `<data>/first-cut/made.json` =
`{version: 1, scripts: {<Script>: {parts: {<part id>: {key, clip, frames}}, cut: {key, clip, frames}}}}`.

A part's `key` is the hash of the request that made it (`Cut.clip`), `clip` its media id in Clips, `frames` the frames
it was rendered with; the cut's `key` is `cut_key`'s (the part keys and the very clips it joined). Nothing of a
prompt, words, seed or verdict is written. A part filed again with no new cut drops the old cut. An entry whose clip
is gone (deleted in Media) is no entry: `of` leaves it out, `write` drops it. The made parts survive a cancel, a
failure and a Hub restart; deleting a part's clip in Media is the redo of that part.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from hub.core.api import Ctx, Invalid

DOC = "made"
VERSION = 1


def doc(ctx: Ctx) -> Any:
    return ctx.doc(DOC, {"version": VERSION, "scripts": {}})


def there(ctx: Ctx, clip: Any) -> Path | None:
    """The clip's real path when it is a clip in Clips that is there, else None."""
    if not isinstance(clip, str) or ctx.files.kind(clip) != "clip":
        return None
    try:
        return Path(os.path.realpath(ctx.files.existing_media(clip)))
    except (Invalid, OSError, ValueError):
        return None


def _entry(ctx: Ctx, entry: Any) -> dict | None:
    ok = isinstance(entry, dict) and isinstance(entry.get("key"), str) and there(ctx, entry.get("clip")) is not None
    return {"key": entry["key"], "clip": entry["clip"], "frames": entry.get("frames")} if ok else None


def of(ctx: Ctx, name: str) -> dict[str, Any]:
    """The script's record, entries whose clip is gone left out: {parts: {id: entry}, cut: entry | None}."""
    held = (doc(ctx).get().get("scripts") or {}).get(name)
    held = held if isinstance(held, dict) else {}
    found = {pid: e for pid, raw in (held.get("parts") or {}).items() if (e := _entry(ctx, raw)) is not None}
    return {"parts": found, "cut": _entry(ctx, held.get("cut"))}


def write(ctx: Ctx, name: str, new_parts: dict[str, dict], cut: dict | None) -> None:
    """The script's record with `new_parts` (and `cut`, when it landed) set, entries whose clip is gone dropped."""
    record = doc(ctx)
    value = record.get()
    scripts = value.get("scripts") if isinstance(value.get("scripts"), dict) else {}
    now = of(ctx, name)
    kept = {**now["parts"], **{pid: {"key": e["key"], "clip": e["clip"], "frames": int(e["frames"])}
                               for pid, e in new_parts.items()}}
    # a part filed again and no new cut: the old cut holds its earlier take, so it is no longer this script's cut
    whole = {"key": cut["key"], "clip": cut["clip"], "frames": int(cut["frames"])} if cut else \
        None if new_parts else now["cut"]
    scripts[name] = {"parts": kept, **({"cut": whole} if whole else {})}
    record.replace({"version": VERSION, "scripts": scripts})


def stamp(ctx: Ctx, clip: Any) -> list | None:
    """[clip id, size, mtime_ns] of a recorded clip that is there, else None."""
    path = there(ctx, clip)
    try:
        st = path.stat() if path is not None else None
    except OSError:
        st = None
    return [clip, st.st_size, st.st_mtime_ns] if st is not None else None


def cut_key(keys: list[str], stamps: list, track: str, size: int, mtime_ns: int, s0: float, end: float,
            wh: list[int]) -> str:
    """The cut's key: sha256 of the part keys and each part's clip (`stamp`: id, size, mtime_ns) in order, the
    track's name, size and mtime_ns, `s0`, `E`, the canvas. A part rendered again changes it even under its old key."""
    clips = [f"{c[0]}|{c[1]}|{c[2]}" for c in stamps]
    body = "\0".join([*keys, *clips, track, str(size), str(mtime_ns), repr(float(s0)), repr(float(end)),
                      f"{wh[0]}x{wh[1]}"])
    return hashlib.sha256(body.encode()).hexdigest()[:16]
