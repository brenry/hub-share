"""The cells of a storyboard: the folder, the cell text format, `put_cell`, `move_cell` and both listings.

A storyboard is a Drive folder exactly one level under the storyboards folder (`Files.storyboards`); its pictures,
sorted by name as Media sorts them, are its cells. A picture put in the folder by hand is a cell at its place. The
cell text is parsed and written here: header lines (`seconds`, `camera`, `cast`, each at most once), a blank line,
the clip text. A text whose first line is no header is all clip text. What is in flight (a drawn picture not landed
yet, the one render drip) is memory only, kept here for the listings and changed by `render.py`.
"""
from __future__ import annotations

import os
import re
from typing import Any

from hub.core.api import Action, Ctx, Invalid, Listing, plain_name

NO_FOLDER = "No storyboards folder is set"
NO_DRIVE = "No Drive folder is set"
NO_BOARD = "No storyboard is called {}"
BAD_NAME = "Use a plain storyboard name, without slashes"
HEADERS = ("seconds", "camera", "cast")
SECONDS_TEXT = "seconds is a number above 0"        # the clip's frames are the model's
PASSING = "~moving-"                       # a cell's name while the cells are renumbered
_HEADER = re.compile(r"^([a-z_]+):\s*(.*)$")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CLIP = re.compile(r"^(\d{2})(?:-(\d+))?\.mp4$")

DRAWS: dict[str, dict[str, Any]] = {}      # job id -> {storyboard, cell, text}: a drawn picture that has not landed
DRIP: dict[str, Any] = {}                  # the one render running: storyboard, cell, job, left, model, saved, facts
ERRORS: dict[str, str] = {}                # storyboard -> why its last render stopped


# ---------------------------------------------------------------- the folder
def top(ctx: Ctx) -> str:
    """The storyboards folder, relative to the Drive; refused while none is set."""
    rel = getattr(ctx.files, "storyboards", None)
    if not rel:
        raise Invalid("storyboard", NO_FOLDER)
    return rel


def board_name(value: Any) -> str:
    """A storyboard's name: one plain folder name (`drive.name_ok`'s rules: no slash, not hidden, within the disk's
    255 bytes), so it stays inside the storyboards folder."""
    name = plain_name(value, "storyboard", "storyboard")
    if name.startswith(PASSING):
        raise Invalid("storyboard", BAD_NAME)
    return name


def _listing(ctx: Ctx, rel: str) -> dict | None:
    try:
        got = ctx.files.folder_list(rel)
    except Invalid:
        return None
    if got.get("unset"):
        raise Invalid("storyboard", NO_DRIVE)
    return got


def boards(ctx: Ctx) -> list[dict]:
    """Each storyboard by name with its number of cells; [] while the storyboards folder is not made yet."""
    rel = top(ctx)
    got = _listing(ctx, rel) or {"dirs": []}
    return [{"name": d, "cells": len(cells_of(ctx, d))} for d in got["dirs"]]


def cells_of(ctx: Ctx, name: str, missing_ok: bool = False) -> list[str]:
    """The picture ids of a storyboard in cell order (one per name: a name held by two types counts once)."""
    got = _listing(ctx, f"{top(ctx)}/{name}")
    if got is None:
        if missing_ok:
            return []
        raise Invalid("storyboard", NO_BOARD.format(name))
    seen: set[str] = set()
    out = []
    for item in got["ids"]:
        stem = os.path.splitext(item.rsplit("/", 1)[-1])[0].casefold()
        if stem not in seen:
            seen.add(stem)
            out.append(item)
    return out


def _make(ctx: Ctx, name: str) -> None:
    """The storyboard's folder, and the storyboards folder above it when it is not there yet."""
    path = ""
    for part in [*top(ctx).split("/"), name]:
        if _listing(ctx, f"{path}/{part}" if path else part) is None:
            ctx.files.folder_new(path, part)
        path = f"{path}/{part}" if path else part


def _stem(item: str) -> str:
    return os.path.splitext(item.rsplit("/", 1)[-1])[0]


def arrange(ctx: Ctx, order: list[str]) -> list[str]:
    """Rename the cells to 01, 02... in `order`: the ones that change go to a passing name first, so no two ever
    share a stem; the text stays in each file. -> the ids in order."""
    out = list(order)
    moving = [k for k, item in enumerate(out) if _stem(item) != f"{k + 1:02d}"]
    for k in moving:
        out[k] = ctx.files.rename_picture(out[k], f"{PASSING}{k + 1:02d}")
    for k in moving:
        out[k] = ctx.files.rename_picture(out[k], f"{k + 1:02d}")
    return out


def next_free(name: str, ids: list[str]) -> int:
    """The next cell's number: after the cells there and the drawn pictures still to land as new cells."""
    waiting = [d["cell"] for d in DRAWS.values() if d["storyboard"] == name]
    return max([len(ids), *waiting]) + 1


def limits(ctx: Ctx, name: str, n: int, ids: list[str]) -> None:
    if n > next_free(name, ids):
        raise Invalid("cell", f"The next cell is {next_free(name, ids)}")


# ---------------------------------------------------------------- the cell text
def parse(text: str) -> dict[str, Any]:
    """{seconds, camera, cast, text} from a cell's text; an unknown or repeated header is refused."""
    lines = text.replace("\r\n", "\n").split("\n")
    first = _HEADER.match(lines[0]) if lines else None
    out: dict[str, Any] = {"seconds": None, "camera": "", "cast": [], "text": text.strip()}
    if not first or first.group(1) not in HEADERS:
        return out
    end = next((k for k, line in enumerate(lines) if not line.strip()), len(lines))
    seen = set()
    for line in lines[:end]:
        m = _HEADER.match(line)
        if not m or m.group(1) not in HEADERS:
            raise Invalid("text", f"Unknown header line \"{line[:40]}\": the headers are seconds, camera and cast")
        key, value = m.group(1), m.group(2).strip()
        if key in seen:
            raise Invalid("text", f"The {key} line is there twice")
        seen.add(key)
        if key == "seconds":
            try:
                secs = float(value)
            except ValueError:
                raise Invalid("text", SECONDS_TEXT) from None
            if not 0 < secs < float("inf"):
                raise Invalid("text", SECONDS_TEXT)
            out["seconds"] = int(secs) if secs.is_integer() else secs
        elif key == "camera":
            out["camera"] = value
        else:
            names = [n.strip() for n in value.split(",") if n.strip()]
            if any("/" in n for n in names):
                raise Invalid("text", "cast is character names, separated by commas")
            out["cast"] = names
    out["text"] = "\n".join(lines[end + 1:]).strip()
    return out


def fields(text: str) -> dict[str, Any]:
    """`parse`, or the whole text as clip text when its headers do not read (a picture dropped in with a text)."""
    try:
        return parse(text)
    except Invalid:
        return {"seconds": None, "camera": "", "cast": [], "text": text.strip()}


def write(cell: dict[str, Any]) -> str:
    """A cell's text from its fields: the headers it has, a blank line, the clip text."""
    head = [f"seconds: {cell['seconds']:g}"] if cell.get("seconds") is not None else []
    head += [f"camera: {cell['camera']}"] if cell.get("camera") else []
    head += [f"cast: {', '.join(cell['cast'])}"] if cell.get("cast") else []
    return "\n".join(head) + ("\n\n" if head else "") + cell.get("text", "")


# ---------------------------------------------------------------- the clips of a storyboard
def clips_of(ctx: Ctx, name: str) -> dict[int, str]:
    """Each cell's newest clip filed for the storyboard (`clips/<YYYY-MM-DD HHMMSS> - <name> <NN>[-n].mp4`, the clips
    root has no subfolders): by its date and time, then n."""
    root = ctx.files.roots.get("clips")
    best: dict[int, tuple[str, int, str]] = {}
    if root is None or not root.is_dir():
        return {}
    filed = re.compile(r"^(\d{4}-\d\d-\d\d \d{6}) - " + re.escape(name) + r" (\d+)(?:-(\d+))?\.mp4$")
    for f in os.listdir(root):
        m = filed.match(f)
        if m:
            key = (m.group(1), int(m.group(3) or 1), f"clips/{f}")
            best[int(m.group(2))] = max(best.get(int(m.group(2)), key), key)
    return {n: v[2] for n, v in best.items()}


# ---------------------------------------------------------------- tools
def _source(ctx: Ctx, picture: str) -> str:
    """A picture to put in: "newest" is the newest Temp picture, any other word a character's name."""
    if picture.strip().casefold() == "newest":
        found = ctx.files.newest_temp()
        if found is None:
            raise Invalid("picture", "Temp holds no picture")
        return found
    found = ctx.files.character(picture.strip())
    if found is None:
        raise Invalid("picture", f"No character is called {picture.strip()}")
    return found


async def put_cell(ctx: Ctx, args: dict) -> dict:
    top(ctx)
    name, picture, text = board_name(args.get("storyboard")), args.get("picture"), args.get("text")
    if picture is None and text is None:
        raise Invalid("cell", "Give the cell a picture, a text or both")
    text = write(parse(text)) if text is not None else None
    return put(ctx, name, args["cell"], _source(ctx, picture) if picture is not None else None, text)


def put(ctx: Ctx, name: str, n: int, src: str | None, text: str | None) -> dict:
    """Make or replace cell `n`: picture `src` put in under the cell's name (its text kept), then `text` written.
    A text for a cell whose drawn picture has not landed waits for it."""
    folder, ids = top(ctx), cells_of(ctx, name, missing_ok=True)
    limits(ctx, name, n, ids)
    if n > len(ids) and src is None:
        held = next((d for d in DRAWS.values() if d["storyboard"] == name and d["cell"] == n), None)
        if held is None:
            raise Invalid("picture", f"Cell {n} has no picture yet; give one")
        held["text"] = text                               # written when the drawn picture lands
        return {"storyboard": name, "cell": n, "waiting": True}
    if n > len(ids) + 1:
        raise Invalid("cell", f"The next cell is {len(ids) + 1}")
    _make(ctx, name)
    if n == len(ids) + 1:
        ids = arrange(ctx, ids)
    item = ids[n - 1] if n <= len(ids) else None
    if src is not None:
        item = ctx.files.put_picture(f"drive/{folder}/{name}", _stem(item) if item else f"{n:02d}", src)
    if text is not None:
        item = ctx.files.picture_text_set(str(item), text)
    return {"storyboard": name, "cell": n, "id": item}


async def move_cell(ctx: Ctx, args: dict) -> dict:
    top(ctx)
    name = board_name(args.get("storyboard"))
    ids = cells_of(ctx, name)
    for key in ("from", "to"):
        if not 1 <= args[key] <= len(ids):
            raise Invalid(key, f"{name} has cells 1 to {len(ids)}")
    order = list(ids)
    order.insert(args["to"] - 1, order.pop(args["from"] - 1))
    return {"storyboard": name, "cells": arrange(ctx, order)}


async def list_storyboards(ctx: Ctx, args: dict) -> dict:
    return {"folder": top(ctx), "storyboards": boards(ctx)}


async def list_storyboard_cells(ctx: Ctx, args: dict) -> dict:
    top(ctx)
    name = board_name(args.get("storyboard"))
    ids, clips = cells_of(ctx, name), clips_of(ctx, name)
    out: dict[str, Any] = {"storyboard": name, "cells": [
        {"cell": k, "id": item, **fields(ctx.files.picture_text(item)), "clip": clips.get(k)}
        for k, item in enumerate(ids, 1)]}
    if DRIP.get("storyboard") == name:
        out["rendering"] = {"cell": DRIP["cell"], "left": list(DRIP["left"])}
    if name in ERRORS:
        out["stopped"] = ERRORS[name]
    return out


NAME = {"type": "string", "minLength": 1, "description": "Name of the storyboard"}
CELL = {"type": "integer", "minimum": 1}
LISTINGS = (
    Listing("storyboards", "Storyboards in the storyboards folder, by name, with the number of cells in each.", {},
            list_storyboards),
    Listing("storyboard_cells", "Cells of one storyboard in order: number, seconds, camera, cast, clip text, and the "
            "cell's newest clip when there is one.", {"storyboard": NAME}, list_storyboard_cells, ("storyboard",)),
)
ACTIONS = (
    Action("put_cell", "Makes or replaces cell N of a storyboard: its picture from a character name or the newest "
           "Temp picture, its text, or both. A first cell makes the storyboard.",
           {"type": "object", "additionalProperties": False, "required": ["storyboard", "cell"], "properties": {
               "storyboard": NAME, "cell": {**CELL, "description": "Number of the cell, from 1"},
               "picture": {"type": "string", "minLength": 1,
                           "description": "A character's name, or newest for the newest Temp picture"},
               "text": {"type": "string", "description": "seconds, camera and cast lines, a blank line, the clip "
                                                         "text"}}}, put_cell),
    Action("move_cell", "Moves cell N of a storyboard to place M; the cells are renumbered 01 onward.",
           {"type": "object", "additionalProperties": False, "required": ["storyboard", "from", "to"], "properties": {
               "storyboard": NAME, "from": {**CELL, "description": "The cell's number now"},
               "to": {**CELL, "description": "Its number after"}}}, move_cell),
)
