"""HTTP routes. LoRA ids are `<family folder>/<path>`, URL-encoded."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from starlette.requests import Request
from starlette.responses import Response

from hub.core.api import Ctx, Invalid

from . import covers, scan, userdata


async def _catalog(ctx: Ctx) -> dict[str, Any]:
    try:
        return await ctx.engine.query("models")
    except Exception as exc:
        raise Invalid("model", (str(exc).strip().splitlines() or ["The engine did not list its models"])[0]) from None


async def _entry(ctx: Ctx, request: Request) -> scan.Entry:
    lora_id = request.query_params.get("id", "")
    fam = scan.families(await _catalog(ctx)).get(lora_id.partition("/")[0])
    entry = await asyncio.to_thread(scan.find, fam, lora_id) if fam else None
    if entry is None:
        raise Invalid("id", "This LoRA is no longer in its folder")
    return entry


def _strength(facts: dict[str, Any]) -> float:
    return facts["weight"] if facts["weight"] is not None else 1.0


def item(ctx: Ctx, entry: scan.Entry, user: dict[str, Any]) -> dict[str, Any]:
    facts = scan.info(entry)
    found = covers.source(entry, facts["thumb"])
    return {
        "id": entry.id, "name": scan.display_name(entry.stem, facts["title"]), "file": entry.rel.rsplit("/", 1)[-1],
        "fileTriggers": facts["triggers"], "cover": {"url": covers.url(entry, found[1])} if found else None,
        "strength": user.get("strength"), "defaultStrength": _strength(facts), "addedAt": entry.mtime,
    }


async def items(ctx: Ctx, model_id: str) -> list[dict[str, Any]]:
    """Every LoRA that fits the model (the engine's folder rule), sorted for the library."""
    fam = scan.family_of(await _catalog(ctx), model_id)
    if fam is None:
        return []
    entries = await asyncio.to_thread(scan.scan, fam)
    users = userdata.reconcile(ctx, fam.key, entries)
    out = await asyncio.to_thread(lambda: [item(ctx, e, users.get(e.id, {})) for e in entries])
    return sorted(out, key=lambda it: (it["name"].lower(), it["id"]))


async def list_loras(ctx: Ctx, request: Request) -> list[dict[str, Any]]:
    return await items(ctx, request.query_params.get("model", ""))


async def patch_user(ctx: Ctx, request: Request) -> dict[str, Any]:
    entry = await _entry(ctx, request)
    try:
        changes = json.loads(await request.body())
    except ValueError:
        raise Invalid("user", "The change is not valid JSON") from None
    return userdata.update(ctx, entry, changes)


async def thumb(ctx: Ctx, request: Request) -> Response:
    size = request.query_params.get("size", "96")
    if size not in {str(s) for s in covers.SIZES}:
        raise Invalid("size", "Size must be 96 or 336")
    entry = await _entry(ctx, request)
    data = await asyncio.to_thread(lambda: covers.thumb(ctx, entry, scan.info(entry)["thumb"], int(size)))
    if data is None:
        return Response(status_code=404)
    return Response(data, media_type="image/webp", headers={"Cache-Control": "no-store"})
