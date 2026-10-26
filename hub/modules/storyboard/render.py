"""Rendering a storyboard and drawing a cell, both through Generate Image's job kind (`generate-image.image`).

The module builds no engine task: it submits the params a Generate press sends and the job builder checks every
value. `render_storyboard` is a drip: one cell's clip waits at a time, and the next cell is submitted when the job
before it finishes (`job.finished`), so the shared queue stays free for other picture jobs. A clip that lands is
filed as `clips/<its day>/<storyboard>/<NN>.mp4` (a redo `NN-2.mp4`). A failed, cancelled or refused cell stops
the drip, and the stop names the cell (`list_storyboard_cells` shows it). A cell's clip model role decides its
pictures: a start-frame model opens on the cell picture, an identity model takes the cast's character pictures and
not the cell picture, a model that takes none gets none. `draw_cell` queues one picture; the picture the job
lands becomes cell N (`Files.put_picture`, so the cell's text stays). Everything in flight is memory only.
"""
from __future__ import annotations

import math
from typing import Any

from hub.core.api import Action, Ctx, Invalid, clip_facts, frames_for, seeds, tier_size

from . import cells, screen

KIND = "generate-image.image"


def _cast(ctx: Ctx, names: list[str]) -> list[str]:
    """The `chars/` ids of the cast, in order; a name no character has is refused."""
    out = []
    for name in names:
        found = ctx.files.character(name)
        if found is None:
            raise Invalid("cast", f"No character is called {name}")
        out.append(found)
    return out


def _seed(saved: dict, n: int) -> dict:
    first = saved.get("seed")
    if not isinstance(first, int) or isinstance(first, bool):
        return {"mode": "none"}                  # no number set: no seed
    return {"mode": "fixed", "value": seeds(first, n, screen.SEED_MAX)[-1]}


def clip_params(ctx: Ctx, run: dict, n: int) -> dict:
    """The params of cell `n`'s clip, as a Generate press sends them; the cell is read from its file now."""
    ids = cells.cells_of(ctx, run["storyboard"])
    if n > len(ids):
        raise Invalid("cells", "the cell is not there now")
    item, facts, saved = ids[n - 1], run["facts"], run["saved"]
    cell = cells.parse(ctx.files.picture_text(item))
    if not cell["text"]:
        raise Invalid("text", "the cell has no clip text")
    width, height = run["size"]
    role = facts["role"] if facts["refs"]["max"] else None
    refs = [item] if role == "start" else _cast(ctx, cell["cast"]) if role == "identity" else []
    params: dict[str, Any] = {"model": run["model"], "mode": "refs" if refs else "new", "prompt": cell["text"],
                              "width": width, "height": height, "frames": frames_for(facts, cell["seconds"]),
                              "steps": saved["steps"], "seed": _seed(saved, n), "loras": []}
    if refs:
        params["references"] = refs
    return params


def _submit_next(ctx: Ctx, run: dict) -> Any:
    """Submit the first cell left; a refusal of the cell's own values names the cell."""
    n = run["cell"] = run["left"].pop(0)
    try:
        job = ctx.jobs.submit(KIND, clip_params(ctx, run, n))
    except Invalid as e:
        raise Invalid(e.field, f"Cell {n}: {e.text}") from None
    run["job"] = job.id
    return job


def _stop(name: str, text: str) -> None:
    cells.ERRORS[name] = text
    cells.DRIP.clear()


async def render_storyboard(ctx: Ctx, args: dict) -> dict:
    cells.top(ctx)
    name = cells.board_name(args.get("storyboard"))
    ids = cells.cells_of(ctx, name)
    wanted = sorted(set(args.get("cells") or range(1, len(ids) + 1)))
    if not ids or wanted[-1] > len(ids):
        raise Invalid("cells", f"{name} has cells 1 to {len(ids)}" if ids else f"{name} has no cells")
    waiting = ctx.jobs.get(cells.DRIP["job"]) if cells.DRIP else None
    if cells.DRIP and (waiting is None or waiting.state in ("done", "failed", "cancelled")):
        _stop(cells.DRIP["storyboard"], f"Cell {cells.DRIP['cell']}: the clip was cancelled")   # gone from the queue
    if cells.DRIP:
        raise Invalid("storyboard", f"{cells.DRIP['storyboard']} is rendering now, cell {cells.DRIP['cell']}")
    saved = screen.saved(ctx)
    if saved["model"] is None:
        raise Invalid("model", "Choose the clip model in the storyboard settings")
    if saved["tier"] is None:
        raise Invalid("tier", "Choose the size tier in the storyboard settings")
    facts = clip_facts(screen.find(await screen.catalog(ctx), saved["model"], clip=True))
    size = tier_size(facts, saved["tier"], saved["aspect"], screen.ratio(saved["aspect"]))
    run = {"storyboard": name, "model": saved["model"], "saved": saved, "facts": facts, "size": size,
           "left": list(wanted)}
    job = _submit_next(ctx, run)
    cells.ERRORS.pop(name, None)
    cells.DRIP.update(run)
    return {"storyboard": name, "cells": wanted, "job": job.id, "state": job.state}


def _picture_size(model: dict, aspect: Any) -> tuple[int, int]:
    """The picture model's own default area at the clips' shape, in multiples of 16."""
    size = model.get("size")
    ok = isinstance(size, list) and len(size) == 2 and all(isinstance(v, int) and v > 0 for v in size)
    w, h = size if ok else (1024, 1024)
    r = screen.ratio(aspect)
    return tuple(int(math.floor(math.sqrt(w * h * x) / 16 + 0.5)) * 16 for x in (r, 1 / r))  # type: ignore[return-value]


async def draw_cell(ctx: Ctx, args: dict) -> dict:
    cells.top(ctx)
    name, n = cells.board_name(args.get("storyboard")), args["cell"]
    ids = cells.cells_of(ctx, name, missing_ok=True)
    cells.limits(ctx, name, n, ids)
    saved = screen.saved(ctx)
    if saved["picture_model"] is None:
        raise Invalid("picture_model", "Choose the picture model in the storyboard settings")
    model = screen.find(await screen.catalog(ctx), saved["picture_model"], clip=False)
    refs = _cast(ctx, args.get("cast") or [])
    width, height = _picture_size(model, saved["aspect"])
    params: dict[str, Any] = {"model": model["id"], "mode": "refs" if refs else "new", "prompt": args["prompt"],
                              "width": width, "height": height, "images": 1, "steps": None, "guidance": None,
                              "seed": {"mode": "none"}, "loras": []}
    if refs:
        params["references"] = refs
    job = ctx.jobs.submit(KIND, params)
    cells.DRAWS[job.id] = {"storyboard": name, "cell": n, "text": None}
    return {"storyboard": name, "cell": n, "job": job.id, "state": job.state}


async def _landed(ctx: Ctx, draw: dict, data: dict) -> None:
    """A drawn picture became cell N (or the next free place, when a cell before it never landed)."""
    name, n = draw["storyboard"], draw["cell"]
    picture = next((o for o in data.get("outputs") or [] if ctx.files.kind(o) == "image"), None)
    if data.get("state") != "done" or picture is None:
        cells.ERRORS[name] = f"Cell {n}: the picture was not made"
        return
    try:
        n = min(n, len(cells.cells_of(ctx, name, missing_ok=True)) + 1)
        cells.put(ctx, name, n, picture, draw["text"])
    except Invalid as e:
        cells.ERRORS[name] = f"Cell {n}: {e.text}"


async def on_finished(ctx: Ctx, data: dict) -> None:
    """`job.finished`: a drawn picture lands as its cell; the drip files its clip and submits the next cell."""
    draw = cells.DRAWS.pop(data.get("job"), None)
    if draw is not None:
        await _landed(ctx, draw, data)
        return
    run = cells.DRIP
    if not run or run.get("job") != data.get("job"):
        return
    name, n = run["storyboard"], run["cell"]
    if data.get("state") != "done":
        job = ctx.jobs.get(data["job"])
        why = job.error if job is not None and job.error else f"the clip was {data.get('state')}"
        _stop(name, f"Cell {n}: {why}")
        return
    try:
        for out in data.get("outputs") or []:
            if ctx.files.kind(out) == "clip":
                ctx.files.file_clip(out, name, f"{n:02d}")
        if not run["left"]:
            cells.DRIP.clear()
            return
        _submit_next(ctx, run)
    except Exception as e:                                   # a refusal (Invalid, or the queue's own) stops the drip
        text = getattr(e, "text", None) or "it could not be queued"
        _stop(name, text if isinstance(e, Invalid) else f"Cell {run['cell']}: {text}")


ACTIONS = (
    Action("draw_cell", "Queues one picture from a picture prompt with the picture model and the cast's character "
           "pictures as references; it becomes cell N when it lands, its text kept.",
           {"type": "object", "additionalProperties": False, "required": ["storyboard", "cell", "prompt"],
            "properties": {"storyboard": cells.NAME, "cell": {**cells.CELL, "description": "Number of the cell"},
                           "prompt": {"type": "string", "minLength": 1, "description": "The picture prompt"},
                           "cast": {"type": "array", "items": {"type": "string", "minLength": 1},
                                    "description": "Character names, as list_characters lists them"}}}, draw_cell),
    Action("render_storyboard", "Queues one clip per cell of a storyboard, every cell or the listed ones, one after "
           "another in cell order.",
           {"type": "object", "additionalProperties": False, "required": ["storyboard"],
            "properties": {"storyboard": cells.NAME,
                           "cells": {"type": "array", "minItems": 1, "items": cells.CELL,
                                     "description": "Cell numbers; every cell when left out"}}}, render_storyboard),
)
