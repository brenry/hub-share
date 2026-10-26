"""HTTP routes: the Temp page (and its groups), the clips page (`root=clips`) or the sounds page (`root=sounds`), the
Drive's folders, favorite (a move inside Temp), the favorite folders (a list of Drive paths, nothing moved), move,
delete; a sound kept as a character's voice (`keep-voice`), the words for a character's voice.
A clip or a sound can be listed and deleted; favorites, the Drive and Characters take pictures only.

Delete and folder removal erase at once (core `Files`): no trash, no confirmation here. After a change
every Media window hears `media.changed` and refreshes what it shows.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from starlette.requests import Request

from hub.core.api import Ctx, Invalid

from . import favorites, library

DELETED = "media.deleted"               # the core event after a delete, {ids}: Edit Video drops gone clips on it


def _changed(ctx: Ctx, what: str, **extra: Any) -> None:
    ctx.bus.publish("changed", "changed", {"what": what, **extra})


async def _body(request: Request) -> dict[str, Any]:
    try:
        body = json.loads(await request.body())
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise Invalid("body", "Send a JSON object")
    return body


def _ids(body: dict[str, Any]) -> list[str]:
    item_ids = body.get("ids")
    if not isinstance(item_ids, list) or not item_ids:
        raise Invalid("ids", "Send at least one item id")
    if not all(library.is_media(i) for i in item_ids):
        raise Invalid("ids", "Only Temp and Drive images")
    return item_ids


def _pictures(item_ids: list[str], text: str) -> list[str]:
    if any(library.is_clip(i) or library.is_sound(i) for i in item_ids):
        raise Invalid("ids", text)
    return item_ids


def _path(body: dict[str, Any], key: str = "path") -> str:
    value = body.get(key, "")
    if not isinstance(value, str):
        raise Invalid(key, "Send a folder path")
    return value


# ---------------------------------------------------------------- the Temp
async def list_media(ctx: Ctx, request: Request) -> dict[str, Any]:
    before, root = request.query_params.get("before") or None, request.query_params.get("root") or "out"
    if root not in library.ROOTS:
        raise Invalid("root", "List out, clips or sounds")
    try:
        limit = int(request.query_params.get("limit", "100"))
    except ValueError:
        limit = 0
    if not 1 <= limit <= 500:
        raise Invalid("limit", "Limit must be 1 to 500")
    return await asyncio.to_thread(library.page, ctx, before, limit, root)


async def favorite(ctx: Ctx, request: Request) -> dict[str, Any]:
    """Favorite = the file moves into its day's Favorites folder; off = back to the day."""
    body = await _body(request)
    ids, on = _pictures(_ids(body), "Only pictures can be favorites"), body.get("on", True)
    if not isinstance(on, bool):
        raise Invalid("on", "Send true or false")
    if not all(library.rel_of(i) for i in ids):
        raise Invalid("ids", "Only Temp images can be favorites")
    moved = await asyncio.to_thread(ctx.files.regroup, ids, library.FAVORITES if on else "")
    _changed(ctx, "favorites")
    return {"moved": [{"from": old, "to": new} for old, new in moved], "on": on}


# ---------------------------------------------------------------- favorite folders
async def favorite_folders(ctx: Ctx, request: Request) -> dict[str, Any]:
    return {"folders": await asyncio.to_thread(favorites.describe, ctx.files, favorites.paths(ctx))}


async def favorite_folder(ctx: Ctx, request: Request) -> dict[str, Any]:
    """Pin a Drive folder under Favorites, or take it off: the list changes, no file or folder does."""
    path, on = favorites.clean(await _body(request))
    if on:
        found = await asyncio.to_thread(favorites.check, ctx.files, path)
        if not found:
            raise await asyncio.to_thread(favorites.refuse, ctx.files, found if found is not None else path)
        path = found
    listed = favorites.pin(ctx, path, on)
    _changed(ctx, "favorite-folders")
    return {"folders": await asyncio.to_thread(favorites.describe, ctx.files, listed)}


# ---------------------------------------------------------------- the Drive
async def drive_list(ctx: Ctx, request: Request) -> dict[str, Any]:
    path = request.query_params.get("path", "")

    def build() -> dict[str, Any]:
        d = ctx.files.folder_list(path)
        items = [library.describe(ctx, i) for i in d["ids"]]
        return {"path": d["path"], "name": d["name"], "dirs": d["dirs"], "items": [i for i in items if i is not None],
                "unset": bool(d.get("unset"))}
    return await asyncio.to_thread(build)


async def drive_folder(ctx: Ctx, request: Request) -> dict[str, Any]:
    body = await _body(request)
    made = await asyncio.to_thread(ctx.files.folder_new, _path(body), body.get("name"))
    _changed(ctx, "drive", path=_path(body))
    return {"path": made}


async def drive_rename(ctx: Ctx, request: Request) -> dict[str, Any]:
    body = await _body(request)
    renamed = await asyncio.to_thread(ctx.files.folder_rename, _path(body), body.get("name"))
    favorites.renamed(ctx, _path(body), renamed)
    _changed(ctx, "drive", path=_path(body).rpartition("/")[0])
    return {"path": renamed}


async def drive_move(ctx: Ctx, request: Request) -> dict[str, Any]:
    body = await _body(request)
    paths = body.get("paths")
    moved = await asyncio.to_thread(ctx.files.folder_move, paths, _path(body, "to"))
    for old, new in zip(paths, moved, strict=True):
        favorites.renamed(ctx, old, new)
    _changed(ctx, "drive", path="")
    return {"paths": moved}


async def drive_remove(ctx: Ctx, request: Request) -> dict[str, Any]:
    body = await _body(request)
    path = _path(body)
    await asyncio.to_thread(ctx.files.folder_remove, path)
    favorites.removed(ctx, path)
    _changed(ctx, "drive", path=path.rpartition("/")[0])
    return {"path": path}


# ---------------------------------------------------------------- characters
async def characters_list(ctx: Ctx, request: Request) -> dict[str, Any]:
    """The Characters folder: each picture with its name; `unset` until the folder is chosen."""
    def build() -> dict[str, Any]:
        if "chars" not in ctx.files.roots:
            return {"unset": True, "items": []}
        items = []
        for c in ctx.files.characters():
            d = library.describe(ctx, c["id"])
            if d is not None:
                items.append({**d, "name": c["name"], "notes": c["notes"], "voice": c["voice"],
                              "sample": c["sample"]})
        return {"unset": False, "items": items}
    return await asyncio.to_thread(build)


async def character_put(ctx: Ctx, request: Request) -> dict[str, Any]:
    """A picture becomes the character called `name` (a copy; the one that had the name is replaced)."""
    body = await _body(request)
    item = body.get("id")
    if library.is_clip(item) or library.is_sound(item):
        raise Invalid("id", "Only pictures can be characters")
    if not library.is_media(item):
        raise Invalid("id", "Only Temp, Drive and Characters images")
    made = await asyncio.to_thread(ctx.files.character_put, body.get("name"), item)
    _changed(ctx, "characters")
    return {"id": made}


async def character_rename(ctx: Ctx, request: Request) -> dict[str, Any]:
    """A character's file takes a new name: {id, name} -> {id}."""
    body = await _body(request)
    made = await asyncio.to_thread(ctx.files.character_rename, body.get("id"), body.get("name"))
    _changed(ctx, "characters")
    return {"id": made}


async def character_remove(ctx: Ctx, request: Request) -> dict[str, Any]:
    """A character's file is erased at once, no trash: {id} -> {name}."""
    body = await _body(request)
    name = await asyncio.to_thread(ctx.files.character_remove, body.get("id"))
    _changed(ctx, "characters")
    return {"name": name}


async def character_notes(ctx: Ctx, request: Request) -> dict[str, Any]:
    """`notes` on a character, saved inside its file: {id, notes} -> {id} ("" clears them)."""
    body = await _body(request)
    made = await asyncio.to_thread(ctx.files.character_notes, body.get("id"), body.get("notes"))
    _changed(ctx, "characters")
    return {"id": made}


async def character_voice(ctx: Ctx, request: Request) -> dict[str, Any]:
    """The words for a character's voice, saved inside its file: {id, voice} -> {id} ("" clears them)."""
    body = await _body(request)
    made = await asyncio.to_thread(ctx.files.character_voice, body.get("id"), body.get("voice"))
    _changed(ctx, "characters")
    return {"id": made}


async def keep_voice(ctx: Ctx, request: Request) -> dict[str, Any]:
    """A sound kept as the voice of a character (`<Name>.wav` beside its picture, replacing): {id, name} -> {id}
    (the character's)."""
    body = await _body(request)
    made = await asyncio.to_thread(ctx.files.keep_voice, body.get("id"), body.get("name"))
    _changed(ctx, "characters")
    return {"id": made}


# ---------------------------------------------------------------- move and delete
async def move(ctx: Ctx, request: Request) -> dict[str, Any]:
    body = await _body(request)
    ids = _pictures(_ids(body), "Only pictures can go to the Drive")
    moved = await asyncio.to_thread(ctx.files.move, ids, _path(body, "to"))
    _changed(ctx, "move", to=_path(body, "to"))
    return {"moved": [{"from": old, "to": new} for old, new in moved]}


async def delete(ctx: Ctx, request: Request) -> dict[str, Any]:
    gone = await asyncio.to_thread(ctx.files.delete, _ids(await _body(request)))
    _changed(ctx, "delete", ids=gone)
    ctx.emit(DELETED, {"ids": gone})
    return {"ids": gone}
