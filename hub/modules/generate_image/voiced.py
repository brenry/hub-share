"""Director's casting: a shot's subject that is in Characters and has no
picture in a box is placed in the next empty box (its picture; its views follow it as for any box). Boxes the
request filled are never moved or replaced; on a model whose boxes are not identities nothing is placed. Its voice, when
it has a sample, goes with the clip as an audio reference (`shotcheck.frame`, `build.clip_job`): no line is made first.
"""
from __future__ import annotations

from typing import Any

from hub.core.api import Ctx

from . import cast, models, routes


def _key(name: Any) -> str:
    return " ".join(str(name or "").split()).lower()


def characters(ctx: Ctx) -> dict[str, dict]:
    return {_key(c["name"]): c for c in ctx.files.characters()}


def cast_named(ctx: Ctx, shot: dict, model: dict) -> list[str]:
    """Each subject that is a listed character without a box goes into the next empty box; -> the names placed."""
    refs = models.picture_refs(model) or {}
    if refs.get("role") != "identity" or not isinstance(shot, dict):
        return []
    part = routes.session_part(ctx)
    boxes = [r for r in part.get("references") or [] if isinstance(r, dict) and isinstance(r.get("id"), str)]
    listed = characters(ctx)
    held = {_key(listed_name) for listed_name, c in listed.items() if any(b["id"] == c["id"] for b in boxes)}
    room = min(cast.BOXES, int(refs.get("max") or cast.BOXES)) - len(boxes)
    placed = []
    for s in shot.get("subjects") or []:
        who = listed.get(_key(s.get("name") if isinstance(s, dict) else None))
        if who is None or _key(who["name"]) in held or room <= 0:
            continue
        size = cast.size(ctx.files.existing_media(who["id"])) or (0, 0)
        boxes.append({"id": who["id"], "w": size[0], "h": size[1]})
        held.add(_key(who["name"]))
        placed.append(who["name"])
        room -= 1
    if placed:
        part["references"] = boxes
    return placed
