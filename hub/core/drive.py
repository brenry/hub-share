"""The Drive: folder operations inside the one Media folder (`Files.roots["drive"]`, set in Settings).

Folder paths are relative, posix, with no empty, `.`, `..` or hidden segments; "" is the root. Every
path is checked by its real path, so a symlink leading out of the Drive is refused. Removing a folder
erases it and everything in it at once: no trash, no confirmation here.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hub.core.api import Invalid

if TYPE_CHECKING:
    from hub.core.files import Files

IMAGES = (".png", ".jpg", ".jpeg", ".webp")
MAX_BYTES = 255                                  # a file name's own limit on the disk, in UTF-8 bytes
BAD_FOLDER = "That folder is not in the Drive"
NO_DRIVE = "Choose the Drive folder in Settings → Storage"


def _rel(path: Any) -> str:
    if not isinstance(path, str) or "\\" in path or "\0" in path or len(path) > 2048:
        raise Invalid("path", BAD_FOLDER)
    parts = [p for p in path.split("/") if p != ""]
    if any(p in (".", "..") or p.startswith(".") for p in parts):
        raise Invalid("path", BAD_FOLDER)
    return "/".join(parts)


def _bytes(name: str) -> int:
    """The name's length in UTF-8 bytes; one that has no UTF-8 form (a lone surrogate) is too long."""
    try:
        return len(name.encode("utf-8"))
    except UnicodeEncodeError:
        return MAX_BYTES + 1


def name_ok(name: Any, room: int = 0) -> str:
    """A folder name as typed: one segment, no slashes, not hidden; `room`: bytes the file name adds to it
    (its type, a temp file's parts), all within `MAX_BYTES`."""
    if not isinstance(name, str):
        raise Invalid("name", "Give the folder a name")
    name = name.strip()
    if (not name or _bytes(name) + room > MAX_BYTES or "/" in name or "\\" in name
            or "\0" in name or name.startswith(".") or name in (".", "..")):
        raise Invalid("name", "Use a plain folder name, without slashes")
    return name


def root(files: Files) -> Path:
    """The Drive's real path; refused until `paths.drive` is set."""
    if "drive" not in files._real:
        raise Invalid("path", NO_DRIVE)
    return files._real["drive"]


def folder(files: Files, path: Any, must_exist: bool = True) -> Path:
    """The real path of a drive folder."""
    rel = _rel(path)
    root_ = root(files)
    real = Path(os.path.realpath(root_ / rel)) if rel else root_
    if os.path.commonpath([root_, real]) != str(root_):
        raise Invalid("path", BAD_FOLDER)
    if must_exist and not real.is_dir():
        raise Invalid("path", BAD_FOLDER)
    return real


def free_name(folder_path: Path, name: str) -> Path:
    """`name` in the folder, or `name (2)`, `name (3)`… when a different file already has it."""
    dest = folder_path / name
    stem, ext = os.path.splitext(name)
    n = 2
    while dest.exists():
        dest = folder_path / f"{stem} ({n}){ext}"
        n += 1
    return dest


def listing(files: Files, path: Any) -> dict:
    """Subfolders and image ids of a drive folder, both sorted by name; `unset` until the Drive is chosen."""
    if "drive" not in files._real:
        return {"path": "", "name": "", "dirs": [], "ids": [], "unset": True}
    real = folder(files, path)
    rel = real.relative_to(root(files)).as_posix() if real != root(files) else ""
    dirs, ids = [], []
    with os.scandir(real) as it:
        for entry in it:
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                dirs.append(entry.name)
            elif entry.is_file() and entry.name.lower().endswith(IMAGES):
                ids.append("drive/" + (f"{rel}/{entry.name}" if rel else entry.name))
    return {"path": rel, "name": real.name, "dirs": sorted(dirs, key=str.lower), "ids": sorted(ids, key=str.lower)}


def make(files: Files, path: Any, name: Any) -> str:
    """A new folder inside `path`. -> its relative path."""
    parent, new = folder(files, path), name_ok(name)
    dest = parent / new
    if dest.exists():
        raise Invalid("name", "A folder with that name is already there")
    dest.mkdir()
    return dest.relative_to(root(files)).as_posix()


def rename(files: Files, path: Any, name: Any) -> str:
    real, new = folder(files, path), name_ok(name)
    if real == root(files):
        raise Invalid("path", "The Drive itself keeps its name")
    dest = real.parent / new
    if dest.exists():
        raise Invalid("name", "A folder with that name is already there")
    real.rename(dest)
    return dest.relative_to(root(files)).as_posix()


def move(files: Files, paths: Any, to: Any) -> list[str]:
    """Move folders into another folder. A folder is never moved into itself. -> the new relative paths."""
    if not isinstance(paths, list) or not paths:          # at least one, no count of the Hub's
        raise Invalid("paths", "Send one or more folders")
    dest = folder(files, to)
    done = []
    for path in paths:
        real = folder(files, path)
        if real == root(files) or os.path.commonpath([real, dest]) == str(real):
            raise Invalid("path", "A folder cannot move into itself")
        if real.parent == dest:
            done.append(real.relative_to(root(files)).as_posix())
            continue
        target = dest / real.name
        if target.exists():
            raise Invalid("path", f"“{real.name}” is already in that folder")
        shutil.move(str(real), str(target))
        done.append(target.relative_to(root(files)).as_posix())
    return done


def remove(files: Files, path: Any) -> None:
    """Erase a folder and everything in it, for good."""
    real = folder(files, path)
    if real == root(files):
        raise Invalid("path", "The Drive itself stays")
    for sub, _dirs, names in os.walk(real):
        for n in names:
            files._drop_thumbs(Path(sub) / n)
    shutil.rmtree(real)


def move_items(files: Files, ids: list[str], to: str) -> list[tuple[str, str]]:
    """`Files.move`: pictures in Temp or the Drive into a Drive folder, a name already there kept."""
    kinds = {files.kind(item) for item in ids if isinstance(item, str)}
    if kinds & {"clip", "sound"}:
        raise Invalid("ids", "Clips stay in the clips folder for now" if "clip" in kinds
                      else "Sounds stay in Sounds")
    dest_dir = folder(files, to)
    moved = []
    for item in ids:
        try:
            src = files.existing_image(item)
        except Invalid:
            continue
        if src.parent == dest_dir:
            continue
        dest = free_name(dest_dir, src.name)
        files._drop_thumbs(src)
        shutil.move(str(src), str(dest))
        moved.append((item, f"drive/{dest.relative_to(root(files)).as_posix()}"))
    return moved
