"""A costume's draft and routes (answers in the `routes` docstring).

A costume draft is a cast's draft keyed (name, costume) in `state`'s map: the character's name, the costume's `variant`,
its pictures `[{id, keep, ignore}]` (boxes 3-9), its `words`, its two approved face frames `faces` (boxes 1-2, as media
ids of its record), `from` (its record's `approved` when it was cast), the seed and model of its last cast, the last
job, what it made and its state; in memory until Approve. Its job is the cast's orbit (124 frames, the six
views) on `<Picture 1>` face-1, `<Picture 2>` face-2, then the costume pictures, with `prompt.costume` (its fields, then
the tab's Prompt box when it holds text). A costume needs the character's
approved cast sheet (`NO_BASE`: none, or an extra's); a costume rename is Remove and cast again.
"""
from __future__ import annotations

import asyncio
from typing import Any

from starlette.requests import Request

from hub.core.api import Ctx, Invalid

from . import prompt, record, routes, state, variants

MAX_COSTUME = 7                                   # Ref2VA's 9 less its two face frames
NO_COSTUME = "Give the costume a picture or words"
TOO_MANY_COSTUME = "A costume takes at most 7 pictures; this has {}"
FACES_GONE = "{}'s approved face frames are gone; cast the character again"
NO_SUCH = "{} has no costume called {}"
FACES = ("face-1", "face-2")


def _faces(name: str, found: dict[str, Any]) -> list[str | None]:
    views = record.ids(name, found)["views"]
    return [views.get(v) for v in FACES]


def fresh(name: str, variant: str, found: dict[str, Any], ent: dict[str, Any] | None) -> dict[str, Any]:
    """A costume before any cast; from its record's entry when it is approved (its pictures as the entry's files)."""
    draft: dict[str, Any] = {
        "name": name, "variant": variant, "state": "none", "faces": _faces(name, found), "pictures": [], "words": "",
        "from": found.get("approved"), "seed": None, "model": None, "job": None, "orbit": None, "views": None,
        "problem": None, "expect": list(record.SHEET)}
    if ent is not None:
        held = ent.get("costume") if isinstance(ent.get("costume"), dict) else {}
        pics = [p for p in held.get("pictures") or [] if isinstance(p, dict)]
        draft.update(state="approved", model=ent.get("model"), words=str(held.get("words") or ""),
                     **{"from": ent.get("from")},
                     pictures=[{"id": i, "keep": str(p.get("keep") or ""), "ignore": str(p.get("ignore") or "")}
                               for i, p in zip(variants.ids(name, ent)["pictures"], pics, strict=True) if i])
    return draft


def current(ctx: Ctx, name: str, variant: str, found: dict[str, Any]) -> dict[str, Any]:
    """The costume's draft in memory, else a fresh one (from the character's record's entry when approved)."""
    hit = variants.entry(found, variant)
    draft = state.get(name, variant)
    if draft is None:
        return fresh(name, hit[0] if hit else variant, found, hit[1] if hit else None)
    if draft["state"] == "rendering" and ctx.jobs.get(draft["job"]) is None:
        draft.update(state="failed", problem=state.CANCELLED)
    return draft


def view(ctx: Ctx, name: str, value: Any) -> dict[str, Any]:
    try:
        variant = variants.name_of(value)
        found = variants.base(ctx, name)
    except Invalid as exc:
        return {"problem": exc.text}
    draft = current(ctx, name, variant, found)
    hit = variants.entry(found, draft["variant"])
    faces = _faces(name, found)
    return {k: v for k, v in draft.items() if k not in state.UNSHOWN} | {
        "faces": faces, "face_thumbs": [ctx.files.thumb_url(f) if f else None for f in faces],
        "record": hit[1] if hit else None, "files": variants.urls(ctx, name, hit[0], hit[1]) if hit else None,
        "prompt": state.box()}


def _cast(ctx: Ctx, draft: dict[str, Any]) -> dict[str, Any]:
    name, variant = draft["name"], draft["variant"]

    def build() -> dict[str, Any]:
        found = variants.base(ctx, name)
        variants.check_folder(ctx, name, variant, found)
        pics = draft["pictures"]
        if not pics and not draft["words"]:
            raise Invalid("pictures", NO_COSTUME)
        if len(pics) > MAX_COSTUME:
            raise Invalid("pictures", TOO_MANY_COSTUME.format(len(pics)))
        for n, pic in enumerate(pics, variants.FIRST_BOX):
            if ctx.files.kind(pic["id"]) != "image":
                raise Invalid("pictures", routes.NOT_A_PICTURE.format(n))
        faces = _faces(name, found)
        for face in faces:
            try:
                ctx.files.existing_image(str(face or ""))
            except Invalid:
                raise Invalid("faces", FACES_GONE.format(name)) from None
        text = prompt.costume(pics, found.get("facts"), draft["words"], state.box())
        draft.update(faces=faces, **{"from": found.get("approved")})
        return {"name": name, "variant": variant, "pictures": [*faces, *(p["id"] for p in pics)], "prompt": text,
                "frames": record.FRAMES, "views": list(record.SHEET.values())}
    return routes.queue(ctx, draft, build)


async def _open(ctx: Ctx, body: dict[str, Any]) -> tuple[str, dict[str, Any] | str]:
    """(its character's name, the costume's draft) for a press, or (the name, the refusal). No such character: 400."""
    name, _ = await asyncio.to_thread(routes._who, ctx, body.get("name"))
    try:
        variant = variants.name_of(body.get("variant"))
        found = await asyncio.to_thread(variants.base, ctx, name)
    except Invalid as exc:
        return name, exc.text
    return name, current(ctx, name, variant, found)


async def get_costume(ctx: Ctx, request: Request) -> dict[str, Any]:
    name, _ = await asyncio.to_thread(routes._who, ctx, request.query_params.get("name"))
    return await asyncio.to_thread(view, ctx, name, request.query_params.get("variant"))


async def post_cast(ctx: Ctx, request: Request) -> dict[str, Any]:
    _, draft = await _open(ctx, body := await routes._body(request))
    if isinstance(draft, str):
        return {"problem": draft}
    if line := routes.set_box(body):
        return {"problem": line}
    if line := routes._busy(ctx, draft):
        return {"problem": line}
    pics = body.get("pictures") if isinstance(body.get("pictures"), list) else []
    draft.update(pictures=[{"id": str(p.get("id") or ""), **routes._lines(p)} for p in pics if isinstance(p, dict)],
                 words=prompt.line(body.get("words")))
    state.put(draft)
    return _cast(ctx, draft)


async def post_again(ctx: Ctx, request: Request) -> dict[str, Any]:
    _, draft = await _open(ctx, await routes._body(request))
    if isinstance(draft, str):
        return {"problem": draft}
    if draft["state"] == "none":
        return {"problem": routes.NOTHING.format(draft["variant"])}
    if line := routes._busy(ctx, draft):
        return {"problem": line}
    state.put(draft)
    return _cast(ctx, draft)


async def post_approve(ctx: Ctx, request: Request) -> dict[str, Any]:
    name, draft = await _open(ctx, await routes._body(request))
    if isinstance(draft, str):
        return {"problem": draft}
    try:
        written = await asyncio.to_thread(variants.approve, ctx, draft)
    except Invalid as exc:
        return {"problem": exc.text}
    except (OSError, ValueError) as exc:               # the character's folder cannot take it: nothing of it was kept
        reason = getattr(exc, "strerror", None) or str(exc) or type(exc).__name__
        return {"problem": record.UNWRITTEN.format(name, reason)}
    draft.update(state="approved", problem=None)
    state.publish(ctx, name, draft["variant"])
    return written


async def post_remove(ctx: Ctx, request: Request) -> dict[str, Any]:
    body = await routes._body(request)
    name, _ = await asyncio.to_thread(routes._who, ctx, body.get("name"))
    try:
        variant = variants.name_of(body.get("variant"))
        removed = await asyncio.to_thread(variants.remove, ctx, name, variant)
    except Invalid as exc:
        return {"problem": exc.text}
    except OSError as exc:
        return {"problem": record.UNWRITTEN.format(name, exc.strerror or str(exc))}
    draft = state.get(name, variant)
    if removed is None and draft is None:
        return {"problem": NO_SUCH.format(name, variant)}
    state.drop(name, variant)
    gone = removed or draft["variant"]                 # type: ignore[index]
    state.publish(ctx, name, gone)
    return {"removed": gone}
