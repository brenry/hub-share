"""The Edit Video tab's HTTP routes, mounted at `/api/sequence` (a paired screen only).

GET `/all`, GET `/one?name=`, POST `/new`, PUT `/one` (`{name, revision, tracks}`, a compare-and-swap on the revision
the window drew from; an item without `out` is the whole clip or sound), POST `/rename`, POST `/delete` (the file
only, never a clip), POST `/join` (queues the save, `join.py`). Every write, and every read that dropped a gone item,
publishes `sequence.changed` {name, revision} to the workspace (a delete: revision -1), so every open window draws
the sequence again. Clips and sounds erased in Media (`DELETED`) are dropped at once from every sequence that held
one, by that same read.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from starlette.requests import Request

from hub.core.api import Ctx, Invalid, Route

BODY = ("name", "revision", "tracks")
ONLY = ("A sequence holds item ids, order, in and out points, where track 2's items start and their level, fades "
        "and duck only")
PUT_LIMIT = 131_072                     # a body's bytes: about 999 items of long clip ids
DELETED = "media.deleted"               # the core event Media emits after a delete, {ids}; this module listens
WRITTEN = "sequence.written"            # the core event a scene emits after writing its sequence


def changed(ctx: Ctx, name: str, revision: int) -> None:
    ctx.bus.publish("changed", "changed", {"name": name, "revision": revision})


async def on_written(ctx: Ctx, data: dict) -> None:
    """A sequence written by a scene's last step: every open window draws it, as after a save here."""
    if isinstance(data.get("name"), str) and isinstance(data.get("revision"), int):
        changed(ctx, data["name"], data["revision"])


def kept(item: dict, fps: float) -> float:
    return round((item["out"] - item["in"]) / fps, 2)


def length(pairs: list[list[tuple[dict, dict]]]) -> float:
    """The seconds a saved file has: track 1's, or up to the end of track 2's last item when track 1 is empty."""
    t1, t2 = pairs
    if t1:
        return sum((it["out"] - it["in"]) / f["fps"] for it, f in t1)
    return max((it["at"] / 1000 + (it["out"] - it["in"]) / f["fps"] for it, f in t2), default=0.0)


def _told(ctx: Ctx, seq: dict) -> dict:
    if seq["dropped"] > 0:
        changed(ctx, seq["name"], seq["revision"])
    return seq


def read(ctx: Ctx, name: Any) -> dict:
    """The sequence (gone clips dropped); a read that dropped one tells every window. On the event loop."""
    return _told(ctx, ctx.files.sequence(name))


async def load(ctx: Ctx, name: Any) -> dict:
    """`read`, its file work in a thread."""
    return _told(ctx, await asyncio.to_thread(ctx.files.sequence, name))


def with_facts(ctx: Ctx, seq: dict) -> list[list[tuple[dict, dict]]]:
    """Each track's items with their facts (a sound on its milliseconds, `fps` 1000); one gone since the read is
    left out."""
    return [[(it, f) for it in track if (f := ctx.files.item_facts(it)) is not None] for track in seq["tracks"]]


def view(ctx: Ctx, seq: dict) -> dict:
    """A sequence as the tab draws it: each item with its kind and id, its file's size, rate, frames, own length,
    kept length, sound and URL."""
    return {"name": seq["name"], "revision": seq["revision"], "tracks": [[
        {**it, "kind": f["kind"], "id": f["id"], "w": f["w"], "h": f["h"], "fps": f["fps"], "frames": f["frames"],
         "seconds": round(f["seconds"], 2), "kept": kept(it, f["fps"]), "audio": f["audio"],
         "url": ctx.files.url(f["id"])} for it, f in track] for track in with_facts(ctx, seq)]}


async def _body(request: Request) -> dict[str, Any]:
    try:
        body = json.loads(await request.body())
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise Invalid("body", "Send a JSON object")
    return body


async def get_all(ctx: Ctx, request: Request) -> dict:
    return {"sequences": await asyncio.to_thread(ctx.files.sequences)}


async def get_one(ctx: Ctx, request: Request) -> dict:
    seq = await load(ctx, request.query_params.get("name"))
    return await asyncio.to_thread(view, ctx, seq)


async def post_new(ctx: Ctx, request: Request) -> dict:
    seq = await asyncio.to_thread(ctx.files.sequence_new, (await _body(request)).get("name"))
    changed(ctx, seq["name"], seq["revision"])
    return view(ctx, seq)


async def put_one(ctx: Ctx, request: Request) -> dict:
    body = await _body(request)
    if set(body) - set(BODY):
        raise Invalid("body", ONLY)
    seq = await asyncio.to_thread(ctx.files.sequence_save, body.get("name"), body.get("tracks"),
                                  body.get("revision"))
    changed(ctx, seq["name"], seq["revision"])
    return await asyncio.to_thread(view, ctx, seq)


async def post_rename(ctx: Ctx, request: Request) -> dict:
    body = await _body(request)
    moved = await asyncio.to_thread(ctx.files.sequence_rename, body.get("name"), body.get("to"))
    changed(ctx, moved["name"], moved["revision"])
    return {"name": moved["name"]}


async def post_delete(ctx: Ctx, request: Request) -> None:
    name = (await _body(request)).get("name")
    await asyncio.to_thread(ctx.files.sequence_delete, name)
    changed(ctx, name.strip(), -1)


async def on_deleted(ctx: Ctx, data: dict) -> None:
    """Clips or sounds erased in Media: every sequence that held one reads again, which drops it, writes the file
    (revision + 1) and tells the windows; a window's save from the older revision is then refused as any stale one
    is."""
    if not any(isinstance(i, str) and ctx.files.kind(i) in ("clip", "sound") for i in data.get("ids") or []):
        return
    for seq in await asyncio.to_thread(ctx.files.sequences):
        with contextlib.suppress(Invalid):
            await load(ctx, seq["name"])


async def post_join(ctx: Ctx, request: Request) -> dict:
    return {"job": ctx.jobs.submit("join", {"name": (await _body(request)).get("name")}).id}


ROUTES = (Route("GET", "/all", get_all),
          Route("GET", "/one", get_one),
          Route("POST", "/new", post_new),
          Route("PUT", "/one", put_one, body_limit=PUT_LIMIT),
          Route("POST", "/rename", post_rename),
          Route("POST", "/delete", post_delete),
          Route("POST", "/join", post_join))
