"""The Storyboard's settings, as the tool server reads and sets them, saved in the module's `settings` document.

Choices are checked against live lists when they are set: the storyboard against the storyboards folder, the two
models against the engine catalog (a clip model, a picture model), the tier against the clip model's tiers and the
aspect against that tier's shapes. A setting left unset reads as null; `seed` reads as "random" or a number in text.
The clip model has no default: until it is chosen a render is refused in one line.
"""
from __future__ import annotations

import re
from typing import Any

from hub.core.api import Ctx, Invalid, Screen, Setting, clip_facts, seed_value, whole

from . import cells

SEED_MAX = 999_999_999
STEPS = (1, 100)
DEFAULTS: dict[str, Any] = {"storyboard": None, "model": None, "picture_model": None, "tier": None, "aspect": "16:9",
                            "steps": None, "seed": "random"}
_ASPECT = re.compile(r"^(\d{1,2}):(\d{1,2})$")
SETTINGS = (
    Setting("storyboard", "choice", text="Name of the open storyboard, as list_storyboards lists it"),
    Setting("model", "choice", text="Id of the clip model the cells render with"),
    Setting("picture_model", "choice", text="Id of the image model draw_cell uses"),
    Setting("tier", "choice", text="Size tier of the clips, as the clip model names it"),
    Setting("aspect", "choice", text="Shape of the clips, one the tier has"),
    Setting("steps", "integer", lo=STEPS[0], hi=STEPS[1], text="Steps the clip model runs"),
    Setting("seed", "seed", lo=0, hi=SEED_MAX, text="Seed of cell 1; cell k uses this seed plus k minus 1"),
)


def saved(ctx: Ctx) -> dict[str, Any]:
    return {**DEFAULTS, **ctx.doc("settings", {}).get()}


def ratio(aspect: Any) -> float:
    """Width over height of an aspect such as 16:9; 16:9 when it does not read."""
    m = _ASPECT.match(aspect) if isinstance(aspect, str) else None
    return int(m.group(1)) / int(m.group(2)) if m and int(m.group(1)) and int(m.group(2)) else 16 / 9


async def catalog(ctx: Ctx) -> dict:
    """The engine catalog, or the engine's own one-line reason as the tool's error."""
    try:
        return await ctx.engine.query("models")
    except Exception as exc:
        raise Invalid("engine", (str(exc).strip().splitlines() or ["The engine did not list its models"])[0]) from None


AGAIN = "Choose the {} model again in the storyboard settings"


def find(cat: dict, model_id: Any, clip: bool) -> dict:
    """A model whose files are there: a clip model (`clip`) or a picture model; else refused. An id another model had
    on the engine line the Hub ran before (its `was`) is refused too: a saved id from that line may name another model
    on this one (upstream's 33B Ref2VA has the fork's pruned Omni's id), so it is chosen again. A model the engine has
    but the Hub cannot drive (`why_not`) is no model."""
    what, field = ("clip", "model") if clip else ("picture", "picture_model")
    models = cat.get("models", [])
    if any(model_id in (m.get("was") or ()) for m in models):
        raise Invalid(field, AGAIN.format(what))
    model = next((m for m in models if m.get("id") == model_id), None)
    if model is None or model.get("status") not in ("available", "partial") or model.get("why_not") \
            or (clip_facts(model) is not None) != clip:
        raise Invalid(field, f"No {what} model with the id {model_id} can run")
    return model


async def read(ctx: Ctx) -> dict:
    cells.top(ctx)
    out = saved(ctx)
    out["seed"] = str(out["seed"])
    return out


def _tier(facts: dict, name: Any) -> dict:
    tier = next((t for t in facts["tiers"] if t["name"] == name), None)
    if tier is None:
        raise Invalid("tier", f"The clip model has the tiers {', '.join(t['name'] for t in facts['tiers'])}")
    return tier


async def write(ctx: Ctx, changes: dict) -> dict:
    cells.top(ctx)
    new = {**saved(ctx), **changes}
    if "storyboard" in changes:
        names = {b["name"].casefold(): b["name"] for b in cells.boards(ctx)}
        name = cells.board_name(changes["storyboard"])
        if name.casefold() not in names:
            raise Invalid("storyboard", cells.NO_BOARD.format(name))
        new["storyboard"] = names[name.casefold()]
    if {"model", "picture_model", "tier", "aspect"} & set(changes):
        cat = await catalog(ctx)
        if "picture_model" in changes:
            find(cat, new["picture_model"], clip=False)
        facts = clip_facts(find(cat, new["model"], clip=True)) if new["model"] is not None else None
        if "tier" in changes:
            if facts is None:
                raise Invalid("tier", "Choose the clip model first")
            _tier(facts, new["tier"])
        if "aspect" in changes and facts is not None and new["tier"] is not None:
            sizes = _tier(facts, new["tier"])["sizes"]
            if new["aspect"] not in sizes:
                raise Invalid("aspect", f"The tier {new['tier']} has the shapes {', '.join(sizes)}")
        elif "aspect" in changes and not _ASPECT.match(new["aspect"]):
            raise Invalid("aspect", "Give the shape as width:height, such as 16:9")
    if "steps" in changes:
        new["steps"] = whole(changes["steps"], "steps", *STEPS, f"Steps must be {STEPS[0]} to {STEPS[1]}")
    if "seed" in changes:
        first = seed_value(changes["seed"], SEED_MAX)
        new["seed"] = "random" if first is None else first
    ctx.doc("settings", {}).replace({k: new[k] for k in DEFAULTS})
    return await read(ctx)


SCREEN = Screen(settings=SETTINGS, read=read, write=write)
