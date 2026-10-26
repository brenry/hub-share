"""Approve: the sheet, orbit and bits copied into the character's folder beside its picture, and its
record.

`approve(ctx, draft)` copies (never moves) the six views into `Characters/<Name>/sheet/<view>.png` (`SHEET`: the frame
each is taken at), the orbit into `orbit.mp4` and each bit into `bits/<n>.<ext>` (n its box, 2-9; its metadata cut,
`api.strip_picture`, as a picture put in Characters), then writes `casting.json` (`api.write_json`):
version, name, role, facts, the headshot's lines, the bits' files and lines, the sheet's files and frames, the orbit's
file, the model's name as the catalog shows it, and when Approve was pressed. No prompt, seed, chat or job: the
character's record, written only on Approve (CLAUDE.md's stated exception, blueprint §13.2). An earlier sheet
is replaced only now and whole: every new file is first copied beside its place under a temporary name (`TEMP`); a copy
that fails erases them all and leaves the earlier sheet, bits and record as they were. Only then is each put in its
place and the record written; a bit of the earlier sheet that this one has not is erased after it, so the record never
names one gone. `read` gives the record (None when it has none), `ids` its files as media ids, and `urls` their
addresses with a version, so a sheet approved again is never the browser's older copy.

An extra's record is `role: "audience"` with its four views (`AUDIENCE`) and its `seat`; a cast
record keeps the `variants` (costumes, `variants.py`) of the record it replaces. Every read-modify-write of the
record holds `LOCK`; `place` is the staging of new files that a costume's approve shares.
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote

from hub.core.api import Ctx, Invalid, strip_picture, write_json

SHEET = {"front": 2, "left": 21, "back": 42, "right": 63, "face-1": 84, "face-2": 113}   # view -> its frame
AUDIENCE = {"front": 2, "left": 21, "right": 63, "face-1": 84}  # an extra's four views
SHEETS = {"cast": SHEET, "audience": AUDIENCE}
FRAMES, EXTRA_FRAMES = 124, 107          # a cast orbit's length, an extra's (73 is not on the lattice)
SIDES, ROWS = ("left", "centre", "right"), 12
SEAT = {"side": "centre", "row": 1}      # a draft's seat before one is set
RECORD, ORBIT, VERSION = "casting.json", "orbit.mp4", 1
LOCK = threading.Lock()                  # one record, two writers (a cast's approve and a costume's)
TEMP = ".{}.hub-new"                     # a new file beside its place until the whole sheet is there
NO_FOLDER = "Choose the Characters folder in Settings → Storage"
NOT_READY = "There is no sheet to approve"
GONE = "{} is not in Characters now"
LOST = "A file of the sheet is gone; cast again"
UNWRITTEN = "Could not write {}'s sheet: {}"
BAD_SEAT = "A seat is a side (left, centre or right) and a row from 1 to 12"
HAS_COSTUMES = "{} has costumes; remove them before casting as audience"


def role_of(found: dict[str, Any] | None) -> str:
    return "audience" if (found or {}).get("role") == "audience" else "cast"


def seat_of(value: Any) -> dict[str, Any]:
    """{side, row} as sent; else `BAD_SEAT`."""
    side, row = (value.get("side"), value.get("row")) if isinstance(value, dict) else (None, None)
    if side not in SIDES or not isinstance(row, int) or isinstance(row, bool) or not 1 <= row <= ROWS:
        raise Invalid("seat", BAD_SEAT)
    return {"side": side, "row": row}


def home(ctx: Ctx, name: str) -> Path:
    """The character's folder, `<Characters>/<Name>/` (not made here)."""
    root = ctx.files.roots.get("chars")
    if root is None:
        raise Invalid("characters", NO_FOLDER)
    return Path(root) / name


def read(ctx: Ctx, name: str) -> dict[str, Any] | None:
    """The character's approved record, else None (none, unreadable, or no Characters folder)."""
    try:
        with open(home(ctx, name) / RECORD, encoding="utf-8") as f:
            found = json.load(f)
    except (OSError, ValueError, Invalid):
        return None
    return found if isinstance(found, dict) else None


def cast(ctx: Ctx, name: str) -> bool:
    """Whether the character's folder holds its record (the Characters listing itself is unchanged)."""
    try:
        return (home(ctx, name) / RECORD).is_file()
    except Invalid:
        return False


def ids(name: str, record: dict[str, Any]) -> dict[str, Any]:
    """The record's files as media ids: {views: {view: id}, bits: [id]} (ids as Media takes them, no version)."""
    def at(rel: Any) -> str | None:
        return f"chars/{name}/{rel}" if isinstance(rel, str) and rel else None
    sheet = record.get("sheet") if isinstance(record.get("sheet"), dict) else {}
    bits = record.get("bits") if isinstance(record.get("bits"), list) else []
    return {"views": {v: at((sheet.get(v) or {}).get("file")) for v in SHEETS[role_of(record)]},
            "bits": [at(b.get("file")) for b in bits if isinstance(b, dict)]}


def urls(ctx: Ctx, name: str, record: dict[str, Any]) -> dict[str, Any]:
    """`ids` plus each file's address with its version (`?v=<its mtime>`, as `Files.url` and `thumb_url` give it):
    {views, bits, view_urls: {view: url}, view_thumbs: {view: url}, bit_urls: [url], orbit_url}. The orbit is no
    media item (an MP4 is one only in the clips root), so it plays from the Casting route `/orbit`."""
    found = ids(name, record)
    try:
        version = f"&v={(home(ctx, name) / ORBIT).stat().st_mtime_ns}"
    except (OSError, Invalid):
        version = ""
    return {**found, "view_urls": {v: ctx.files.url(i) if i else None for v, i in found["views"].items()},
            "view_thumbs": {v: ctx.files.thumb_url(i) if i else None for v, i in found["views"].items()},
            "bit_urls": [ctx.files.url(i) if i else None for i in found["bits"]],
            "orbit_url": f"/api/casting/orbit?name={quote(name)}{version}"}


def _source(ctx: Ctx, item: Any) -> Path:
    try:
        return ctx.files.existing_media(str(item))
    except Invalid:
        raise Invalid("approve", LOST) from None


def _staged(folder: Path, rel: str) -> Path:
    return folder / Path(rel).parent / TEMP.format(Path(rel).name)


def _drop(paths: list[Path]) -> None:
    """The temporary files, and what `strip_picture` may have left beside one."""
    for tmp in paths:
        tmp.unlink(missing_ok=True)
        tmp.with_name(f".{tmp.name}.clean").unlink(missing_ok=True)


def place(folder: Path, files: dict[str, Path], strip: Callable[[str], bool]) -> None:
    """Every file of `files` ({rel: source}) copied beside its place under `TEMP` (those `strip` names cut of their
    metadata), then each moved into place. A copy that fails erases every temporary file and every folder this made,
    and raises (`OSError`, or `ValueError` for a picture that is none): what was there stays whole."""
    staged: list[Path] = []
    subs = sorted({(folder / rel).parent for rel in files} | {folder}, key=lambda d: len(d.parts))
    made = [d for d in subs if not d.exists()]
    try:
        for d in subs:
            d.mkdir(parents=True, exist_ok=True)
        for rel, src in files.items():                 # a source may be a file this replaces: copied aside first
            staged.append(_staged(folder, rel))
            shutil.copyfile(src, staged[-1])
            if strip(rel):
                strip_picture(staged[-1])
        for rel in files:
            os.replace(_staged(folder, rel), folder / rel)
    except (OSError, ValueError):
        _drop(staged)
        for d in reversed(made):                       # a folder this made, left empty: gone too
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        raise


def now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def approve(ctx: Ctx, draft: dict[str, Any]) -> dict[str, Any]:
    """The draft's sheet written to the character's folder (the module docstring); -> the record written. A file
    that cannot be written is `OSError` (or `ValueError`: a bit that is no picture), every new file erased; the earlier
    sheet stays whole."""
    made_as = draft.get("cast_as") or draft.get("role")      # the role its views were cast as
    name, role = draft["name"], "audience" if made_as == "audience" else "cast"
    sheet = SHEETS[role]
    views, orbit = draft.get("views") or {}, draft.get("orbit")
    if draft.get("state") != "ready" or not orbit or set(views) != set(sheet):
        raise Invalid("approve", NOT_READY)
    if ctx.files.character(name) is None:
        raise Invalid("name", GONE.format(name))
    folder = home(ctx, name)
    files = {f"sheet/{view}.png": _source(ctx, views[view]) for view in sheet}
    files[ORBIT] = _source(ctx, orbit)
    bits = []
    for n, bit in enumerate(draft.get("bits") or [], 2):
        src = _source(ctx, bit["id"])
        bits.append((f"bits/{n}{src.suffix.lower()}", bit))
        files[bits[-1][0]] = src
    with LOCK:
        before = read(ctx, name) or {}
        variants = before.get("variants") if isinstance(before.get("variants"), dict) else {}
        if role == "audience" and variants:
            raise Invalid("role", HAS_COSTUMES.format(name))
        place(folder, files, lambda rel: rel.startswith("bits/"))
        (folder / "bits").mkdir(exist_ok=True)
        head, facts = draft.get("headshot") or {}, draft.get("facts") or {}
        record = {"version": VERSION, "name": name, "role": role,
                  "facts": {"age": facts.get("age", ""), "build": facts.get("build", "")},
                  "headshot": {"keep": head.get("keep", ""), "ignore": head.get("ignore", "")},
                  "bits": [{"file": rel, "keep": b.get("keep", ""), "ignore": b.get("ignore", "")} for rel, b in bits],
                  "sheet": {view: {"file": f"sheet/{view}.png", "frame": frame} for view, frame in sheet.items()},
                  "orbit": ORBIT, "model": draft.get("model") or "", "approved": now()}
        if role == "audience":
            record["seat"] = seat_of(draft.get("seat") or SEAT)
        elif variants:
            record["variants"] = variants
        write_json(folder / RECORD, record, 0o644)
        for old in (folder / "bits").iterdir():        # after the record, under the lock: never a bit it names
            if old.is_file() and not old.name.startswith(".") and f"bits/{old.name}" not in files:
                old.unlink(missing_ok=True)
        for view in set(SHEET) | set(AUDIENCE):        # a view of the earlier sheet that this one has not
            if view not in sheet:
                (folder / "sheet" / f"{view}.png").unlink(missing_ok=True)
    return record
