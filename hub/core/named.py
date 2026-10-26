"""Named pictures in the Characters and Drive folders, and the one text field such a picture may hold.

A named picture is a file whose stem is its name, in one of these folders: the top of Characters (`chars/<file>`)
or a Drive folder (`drive/<path>/<file>`). Here: put a picture in under a name (a copy, its metadata cut out,
replacing every picture of that stem), rename one (its type and text kept; a stem another picture in the folder has
is refused), and the text field (`pngtext`, the only writer) with the folders allowed to hold it: `chars/<file>` at the
top of Characters and, once the storyboards folder is set (`paths.storyboards`, `Files.set_storyboards`),
`drive/<storyboards>/<name>/<file>`, exactly one level under it. The text belongs to the name: a rename and a new
picture put under the name keep it (both fields, on a character: notes and voice). `characters.py` keeps its
listing and its policy and calls into this file.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from hub.core import clean, drive, pngtext
from hub.core.api import Invalid

if TYPE_CHECKING:
    from hub.core.files import Files

NO_CHARS = "Choose the Characters folder in Settings → Storage"
NOT_YOURS = "That is not a folder of named pictures (Characters, or a Drive folder)"
GONE = "That picture is not in its folder now"
NO_TEXT = "That picture cannot hold text"
TAKEN = "A picture in that folder is already called {}"
UNREADABLE = "That image could not be read"


def pictures(folder: Path) -> list[Path]:
    """The pictures at the top of the folder, newest first, so a name held by two files (Character 1.png and
    Character 1.jpg) is the newer one's."""
    found = []
    with os.scandir(folder) as it:
        for entry in it:
            if not entry.name.startswith(".") and entry.is_file() and entry.name.lower().endswith(drive.IMAGES):
                found.append(Path(entry.path))
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)


def named(folder: Path, name: str) -> list[Path]:
    """The pictures of the folder with that stem (any case), newest first."""
    return [p for p in pictures(folder) if p.stem.casefold() == name.casefold()]


def chars_root(files: Files) -> Path:
    if "chars" not in files._real:
        raise Invalid("characters", NO_CHARS)
    return files._real["chars"]


def folder_of(files: Files, folder: object) -> tuple[Path, str]:
    """The real path of a folder that holds named pictures and its id prefix: "chars" (the top of Characters) or
    "drive/<relative path>" (a Drive folder that is there; "drive" is the Drive itself). Anything else is refused."""
    if folder == "chars":
        return chars_root(files), "chars"
    if isinstance(folder, str) and (folder == "drive" or folder.startswith("drive/")):
        real = drive.folder(files, folder[6:])
        rel = real.relative_to(drive.root(files)).as_posix()
        return real, "drive" if rel == "." else f"drive/{rel}"
    raise Invalid("folder", NOT_YOURS)


def own(files: Files, item_id: object) -> tuple[Path, Path, str]:
    """A named picture that is there: (its folder's real path, its file, the folder's id prefix)."""
    if not isinstance(item_id, str) or not item_id.startswith(("chars/", "drive/")):
        raise Invalid("id", NOT_YOURS)
    folder_id, _, name = item_id.rpartition("/")
    folder, prefix = folder_of(files, folder_id)
    src = folder / name
    if (not name or name.startswith(".") or "\\" in name or "\0" in name or not name.lower().endswith(drive.IMAGES)
            or Path(os.path.realpath(src)).parent != folder or not src.is_file()):
        raise Invalid("id", GONE)
    return folder, src, prefix


def text_allowed(files: Files, item_id: object) -> bool:
    """Whether `item_id` is a picture place allowed to hold text: `chars/<file>` at the top of Characters, or
    `drive/<storyboards>/<name>/<file>` exactly one level under the storyboards folder once that is set."""
    if not isinstance(item_id, str) or "\0" in item_id or "\\" in item_id:
        return False
    parts = item_id.split("/")
    if any(p in ("", ".", "..") or p.startswith(".") for p in parts):
        return False
    if parts[0] == "chars":
        return len(parts) == 2 and "chars" in files._real
    boards = getattr(files, "storyboards", None)
    if parts[0] != "drive" or not boards or "drive" not in files._real:
        return False
    head = boards.split("/")
    if len(parts) != len(head) + 3 or parts[1:len(head) + 1] != head:
        return False
    try:
        top = drive.folder(files, boards)
    except Invalid:
        return False
    return Path(os.path.realpath(files._real["drive"].joinpath(*parts[1:]))).parent.parent == top


def read_text(files: Files, item_id: object) -> str:
    """The text inside a picture of an allowed folder; "" elsewhere, for a non-PNG and for an unreadable file."""
    if not text_allowed(files, item_id):
        return ""
    try:
        return pngtext.read(files.existing_image(str(item_id)))
    except Invalid:
        return ""


def write_text(files: Files, folder: Path, src: Path, text: str, key: str = pngtext.KEY) -> Path:
    """`src` again as `<stem>.png` holding `text` as its `key` field ("" clears it; the other field kept), pixel for
    pixel; its thumbnails dropped and any older file of the same stem erased. No checks: the caller's. -> the PNG."""
    files._drop_thumbs(src)
    try:
        dest = pngtext.write(src, text, key)
    except (OSError, ValueError):
        raise Invalid("image", UNREADABLE) from None
    for p in named(folder, src.stem):
        if p != dest:
            files._drop_thumbs(p)
            p.unlink(missing_ok=True)
    return dest


def set_text(files: Files, item_id: object, text: object) -> str:
    """Save `text` inside a picture of an allowed folder (a module checks its own bound first). -> the new id."""
    if not text_allowed(files, item_id):
        raise Invalid("id", NO_TEXT)
    if not isinstance(text, str) or "\0" in text:
        raise Invalid("text", "Send the text as text")
    if len(text) > pngtext.MAX:
        raise Invalid("text", f"Text is at most {pngtext.MAX:,} characters")
    folder, src, prefix = own(files, item_id)
    return f"{prefix}/{write_text(files, folder, src, text).name}"


def put(files: Files, folder: object, name: object, item_id: str) -> str:
    """Make `item_id`'s picture the one called `name` in `folder` ("chars" or "drive/<path>"): copied in as
    <name>.<its type>, metadata cut out, replacing every picture of that stem; the replaced picture's text stays with
    the name where the folder allows text. -> the picture's id."""
    clean_name = drive.name_ok(name)
    where, prefix = folder_of(files, folder)
    src = files.existing_image(item_id)
    dest = where / f"{clean_name}{src.suffix.lower()}"
    old = named(where, clean_name)
    if src.parent == where and src.stem.casefold() == clean_name.casefold():
        return f"{prefix}/{src.name}"
    tmp = where / f".{clean_name}.hub-new"
    shutil.copyfile(src, tmp)
    try:
        clean.strip(tmp)
    except (OSError, ValueError):
        tmp.unlink(missing_ok=True)
        raise Invalid("image", UNREADABLE) from None
    kept = pngtext.fields(old[0]) if old and text_allowed(files, f"{prefix}/{dest.name}") else {}
    for p in old:
        files._drop_thumbs(p)
        if p != dest:
            p.unlink(missing_ok=True)
    os.replace(tmp, dest)
    for key, text in kept.items():                              # the name's text stays with the name
        dest = write_text(files, where, dest, text, key)
    return f"{prefix}/{dest.name}"


def rename(files: Files, item_id: object, name: object, taken: str = TAKEN) -> str:
    """The picture's file takes the new stem (its type and text kept); an older file left under the old stem goes
    too, so the old name is gone. A stem another picture of the folder has is refused (`taken`). -> the new id."""
    folder, src, prefix = own(files, item_id)
    new = drive.name_ok(name)
    if any(p != src for p in named(folder, new)):
        raise Invalid("name", taken.format(new))
    dest = folder / f"{new}{src.suffix}"
    files._drop_thumbs(src)
    os.rename(src, dest)
    for p in named(folder, src.stem):
        if p != dest:                                       # a change of case only: the file renamed is the one kept
            files._drop_thumbs(p)
            p.unlink(missing_ok=True)
    return f"{prefix}/{dest.name}"
