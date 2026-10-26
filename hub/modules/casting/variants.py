"""Costumes on a character's record: a costume's folder `Characters/<Name>/<costume>/` and its entry
in its `casting.json` under `variants`.

A costume's name is a plain name (`plain_name`), not `sheet` or `bits` (the cast's folders, any case), one per
case-folded name. Approve copies its six views into `<costume>/sheet/<view>.png`, its orbit into `<costume>/orbit.mp4`
and each costume picture into `<costume>/costume/<n>.<ext>` (n its box, 3-9; its metadata cut), staged and moved as the
character's own sheet is (`record.place`); then, holding `record.LOCK`, its record is read again and written with
`variants[<costume>]` = {from, costume: {words, pictures: [{file, keep, ignore}]}, sheet: {view: {file, frame}}, orbit,
model, approved}; every other key of the record as it was. Paths are relative to the character's folder, so a rename
carries them. A costume picture of an earlier approve that this one has not is erased after the record. `from` is the
character's own record's `approved` when the costume was cast: a costume whose `from` is not its record's `approved` now
was cast from an earlier face (`earlier`). Remove writes the record without the entry first, then erases the folder
(only a direct child of the character's folder that its `variants` names). A folder of the costume's name in that folder
that is not its costume is refused (`NOT_ITS`).
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from urllib.parse import quote

from hub.core.api import Ctx, Invalid, plain_name, write_json

from . import record

RESERVED = ("sheet", "bits")                     # the cast's folders in the character's folder
COSTUME = "costume"                              # the costume pictures' folder inside a costume's
FIRST_BOX = 3                                    # boxes 1-2 are its face frames
NO_BASE = "Approve {}'s sheet as cast before a costume"
RESERVED_LINE = "{} is a name Casting uses; choose another"
NOT_ITS = "A folder called {} is in {}'s folder and is not a costume of the character"


def name_of(value: Any) -> str:
    """The costume's name as typed, trimmed; else one line."""
    variant = plain_name(value, "variant", "costume")
    if variant.casefold() in RESERVED:
        raise Invalid("variant", RESERVED_LINE.format(variant))
    return variant


def entries(found: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    held = (found or {}).get("variants")
    return {k: v for k, v in held.items() if isinstance(v, dict)} if isinstance(held, dict) else {}


def entry(found: dict[str, Any] | None, variant: str) -> tuple[str, dict[str, Any]] | None:
    """(its name as the record has it, its entry), the name matched in any case; else None."""
    return next(((k, v) for k, v in entries(found).items() if k.casefold() == variant.casefold()), None)


def base(ctx: Ctx, name: str) -> dict[str, Any]:
    """The character's approved record when it is cast (not audience); else `NO_BASE`."""
    found = record.read(ctx, name)
    if found is None or record.role_of(found) != "cast":
        raise Invalid("variant", NO_BASE.format(name))
    return found


def check_folder(ctx: Ctx, name: str, variant: str, found: dict[str, Any] | None) -> None:
    """Refused when the character's folder holds something of the costume's name (in any case: a
    case-insensitive drive does not tell them apart) that its record does not name as a costume."""
    if entry(found, variant) is not None:
        return
    try:
        there = [p.name for p in record.home(ctx, name).iterdir() if p.name.casefold() == variant.casefold()]
    except OSError:
        there = []
    if there:
        raise Invalid("variant", NOT_ITS.format(there[0], name))


def orbit_path(ctx: Ctx, name: str, variant: str) -> Path | None:
    """The approved costume's orbit, when the character's record names the costume."""
    hit = entry(record.read(ctx, name), variant)
    return None if hit is None else record.home(ctx, name) / hit[0] / record.ORBIT


def ids(name: str, ent: dict[str, Any]) -> dict[str, Any]:
    """The entry's files as media ids: {views: {view: id}, pictures: [id]}."""
    def at(rel: Any) -> str | None:
        return f"chars/{name}/{rel}" if isinstance(rel, str) and rel else None
    sheet = ent.get("sheet") if isinstance(ent.get("sheet"), dict) else {}
    held = ent.get("costume") if isinstance(ent.get("costume"), dict) else {}
    pictures = held.get("pictures") if isinstance(held.get("pictures"), list) else []
    return {"views": {v: at((sheet.get(v) or {}).get("file")) for v in record.SHEET},
            "pictures": [at(p.get("file")) for p in pictures if isinstance(p, dict)]}


def urls(ctx: Ctx, name: str, variant: str, ent: dict[str, Any]) -> dict[str, Any]:
    """`ids` plus each file's address with its version, as `record.urls` gives the character's own."""
    found = ids(name, ent)
    try:
        version = f"&v={(record.home(ctx, name) / variant / record.ORBIT).stat().st_mtime_ns}"
    except (OSError, Invalid):
        version = ""
    return {**found, "view_urls": {v: ctx.files.url(i) if i else None for v, i in found["views"].items()},
            "view_thumbs": {v: ctx.files.thumb_url(i) if i else None for v, i in found["views"].items()},
            "picture_urls": [ctx.files.url(i) if i else None for i in found["pictures"]],
            "orbit_url": f"/api/casting/orbit?name={quote(name)}&variant={quote(variant)}{version}"}


def listing(ctx: Ctx, name: str, found: dict[str, Any] | None, drafts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The chips: [{variant, state, approved, earlier, thumb}], its record's costumes, then those only in memory."""
    held = {d["variant"].casefold(): d for d in drafts}
    out = []
    for key, ent in entries(found).items():
        draft = held.pop(key.casefold(), None)
        front = ids(name, ent)["views"]["front"]
        out.append({"variant": key, "state": draft["state"] if draft else "approved", "approved": True,
                    "earlier": ent.get("from") != (found or {}).get("approved"),
                    "thumb": ctx.files.thumb_url(front) if front else None})
    for draft in held.values():
        front = (draft.get("views") or {}).get("front")
        out.append({"variant": draft["variant"], "state": draft["state"], "approved": False, "earlier": False,
                    "thumb": ctx.files.thumb_url(front) if front else None})
    return out


def _source(ctx: Ctx, item: Any) -> Path:
    try:
        return ctx.files.existing_media(str(item))
    except Invalid:
        raise Invalid("approve", record.LOST) from None


def approve(ctx: Ctx, draft: dict[str, Any]) -> dict[str, Any]:
    """The costume draft written to the character's folder (the module docstring); -> the entry written. A file
    that cannot be written is `OSError` or `ValueError`, every new file erased; what was there stays whole."""
    name, views, orbit = draft["name"], draft.get("views") or {}, draft.get("orbit")
    if draft.get("state") != "ready" or not orbit or set(views) != set(record.SHEET):
        raise Invalid("approve", record.NOT_READY)
    if ctx.files.character(name) is None:
        raise Invalid("name", record.GONE.format(name))
    files = {f"sheet/{view}.png": _source(ctx, views[view]) for view in record.SHEET}
    files[record.ORBIT] = _source(ctx, orbit)
    pictures = []
    for n, pic in enumerate(draft.get("pictures") or [], FIRST_BOX):
        src = _source(ctx, pic["id"])
        pictures.append((f"{COSTUME}/{n}{src.suffix.lower()}", pic))
        files[pictures[-1][0]] = src
    with record.LOCK:
        found = base(ctx, name)
        hit = entry(found, draft["variant"])
        key = (hit or (draft["variant"],))[0]
        check_folder(ctx, name, key, found)
        folder = record.home(ctx, name) / key
        record.place(folder, files, lambda rel: rel.startswith(f"{COSTUME}/"))
        (folder / COSTUME).mkdir(exist_ok=True)
        ent = {"from": draft.get("from") or "",
               "costume": {"words": draft.get("words") or "",
                           "pictures": [{"file": f"{key}/{rel}", "keep": p.get("keep", ""),
                                         "ignore": p.get("ignore", "")} for rel, p in pictures]},
               "sheet": {v: {"file": f"{key}/sheet/{v}.png", "frame": f} for v, f in record.SHEET.items()},
               "orbit": f"{key}/{record.ORBIT}", "model": draft.get("model") or "", "approved": record.now()}
        found = record.read(ctx, name) or found
        found["variants"] = {**entries(found), key: ent}
        try:
            write_json(record.home(ctx, name) / record.RECORD, found, 0o644)
        except OSError:
            if hit is None:                            # a new costume's folder, named by no record: not stranded
                shutil.rmtree(folder, ignore_errors=True)
            raise
        for old in (folder / COSTUME).iterdir():       # after the record, under the lock: never a picture it names
            if old.is_file() and not old.name.startswith(".") and f"{COSTUME}/{old.name}" not in files:
                old.unlink(missing_ok=True)
    return ent


def remove(ctx: Ctx, name: str, variant: str) -> str | None:
    """The costume gone from its record, then its folder; -> its name, or None when its record has no such costume."""
    with record.LOCK:
        found = record.read(ctx, name)
        hit = entry(found, variant)
        if found is None or hit is None:
            return None
        rest = {k: v for k, v in entries(found).items() if k != hit[0]}
        found.pop("variants", None)
        if rest:
            found["variants"] = rest
        own = record.home(ctx, name)
        write_json(own / record.RECORD, found, 0o644)
        folder = own / hit[0]
        if folder.parent == own and folder.is_dir() and not folder.is_symlink():
            shutil.rmtree(folder)
    return hit[0]
