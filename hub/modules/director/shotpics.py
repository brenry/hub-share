"""A shot's own pictures: pictures dragged from Media onto a shot in the Storyboard, no
character made of them. When a shot holds any, its clip takes exactly those, in the shot's order, as <Picture 1>,
<Picture 2>, ... (in place of the cast's pictures), on a model that takes pictures; for a pasted H3 prompt that names
them. Kept in the Hub's data (`DOC`: {script: {shot id: [item ids]}}), not in the script file."""
from __future__ import annotations

from typing import Any

from hub.core.api import Ctx, Invalid

DOC = "shotpictures"
MOST = 9


def get(ctx: Ctx, name: str, sid: str) -> list[str]:
    return list(((ctx.doc(DOC, {}).get() or {}).get(name) or {}).get(sid) or [])


def put(ctx: Ctx, name: str, sid: str, ids: Any) -> dict[str, Any]:
    if not isinstance(ids, list) or len(ids) > MOST or not all(isinstance(i, str) and i for i in ids):
        raise Invalid("ids", f"A shot holds 0 to {MOST} pictures")
    for i in ids:
        if ctx.files.kind(i) != "image":
            raise Invalid("ids", "Only pictures go on a shot")
        ctx.files.existing_image(i)
    doc = ctx.doc(DOC, {})
    held = dict((doc.get() or {}).get(name) or {})
    if ids:
        held[sid] = list(ids)
    else:
        held.pop(sid, None)
    doc.patch({name: held})
    return {"pictures": held}


def all_of(ctx: Ctx, name: str) -> dict[str, list[str]]:
    return dict((ctx.doc(DOC, {}).get() or {}).get(name) or {})
