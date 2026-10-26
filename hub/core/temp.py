"""The Hub's own roots, Temp (`out/<day>/...`) and the clips (`clips/<day>/...`): grouping Temp pictures inside a
day (Favorites), filing a clip under a group with a name (the storyboard's), and the newest Temp picture.

A file stays in its own root and its own day folder: a group is one folder inside the day (`<day>/<group>/`). Names
follow the Drive's rules (`drive.name_ok`). Temp names are the time a file came in (`HHMMSS-mmm[-n]`, `temp_path`),
so the newest picture is the last day folder's last time name, whatever group it sits in.
"""
from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING

from hub.core import drive
from hub.core.api import Invalid

if TYPE_CHECKING:
    from hub.core.files import Files

CLIPS = "clips"
NOT_A_CLIP = "That is not a clip"
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME = re.compile(r"^(\d{6}-\d{3})(?:-(\d+))?$")


def regroup(files: Files, ids: list[str], group: str) -> list[tuple[str, str]]:
    """Move Temp files into `<day>/<group>/` (`group` "": the day folder itself); anything else is skipped.
    -> (old id, new id) each."""
    moved = []
    for item in ids:
        parts = item.split("/")
        if parts[0] != "out" or len(parts) < 3:
            continue
        try:
            src = files.existing_media(item)
        except Invalid:
            continue
        root = files.roots["out"]
        dest_dir = root / parts[1] / group if group else root / parts[1]
        if src.parent == dest_dir:
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = drive.free_name(dest_dir, src.name)
        files._drop_thumbs(src)
        shutil.move(str(src), str(dest))
        if group == "" and not any(src.parent.iterdir()):
            src.parent.rmdir()
        moved.append((item, f"out/{dest.relative_to(root).as_posix()}"))
    return moved


def _plain(value: object, field: str, what: str, room: int = 0) -> str:
    try:
        return drive.name_ok(value, room)
    except Invalid:
        raise Invalid(field, f"Use a plain {what} name, without slashes") from None


def file_clip(files: Files, item_id: str, group: str, name: str) -> str:
    """Rename a clip of the clips root to `clips/<YYYY-MM-DD HHMMSS> - <group> <name>.mp4` in the root itself (no
    subfolders); a name taken by another file becomes `-2`, `-3`. -> the new id."""
    parts = item_id.split("/") if isinstance(item_id, str) else []
    if len(parts) < 2 or parts[0] != CLIPS or files.kind(item_id) != "clip":
        raise Invalid("item", NOT_A_CLIP)
    src = files.existing_media(item_id)
    group, name = _plain(group, "group", "group"), _plain(name, "name", "clip")
    folder = root = files.roots[CLIPS]
    stem = f"{time.strftime('%Y-%m-%d %H%M%S', time.localtime(src.stat().st_mtime))} - {group} {name}"
    dest, n = folder / f"{stem}.mp4", 2
    while dest.exists() and dest != src:
        dest, n = folder / f"{stem}-{n}.mp4", n + 1
    if dest != src:
        files._drop_thumbs(src)
        shutil.move(str(src), str(dest))
    return f"{CLIPS}/{dest.relative_to(root).as_posix()}"


def _time_key(path: Path) -> tuple:
    """A Temp file's place in its day: its time name, then its `-n`; a name that is not a time sorts first."""
    m = _TIME.match(path.stem)
    return (1, m.group(1), int(m.group(2) or 1)) if m else (0, path.stem, 0)


def newest_temp(files: Files) -> str | None:
    """The newest picture in Temp by its day folder and then its time name, whatever group it sits in (a day's
    `Favorites/` does not outrank a later loose picture); hidden files (half taken in) are skipped. None when Temp
    holds no picture."""
    root = files.roots["out"]
    if not root.is_dir():
        return None
    days = sorted((d for d in os.scandir(root) if d.is_dir() and _DAY.match(d.name)), key=lambda d: d.name,
                  reverse=True)
    for day in days:
        found = [Path(sub) / n for sub, dirs, names in os.walk(day.path)
                 for n in names if not n.startswith(".") and n.lower().endswith(drive.IMAGES)
                 and not any(part.startswith(".") for part in Path(sub).relative_to(day.path).parts)]
        if found:
            return f"out/{max(found, key=_time_key).relative_to(root).as_posix()}"
    return None
