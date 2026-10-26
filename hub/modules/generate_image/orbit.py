"""A character's orbit: the Casting tab's one clip on a Ref2VA model, then its views taken from it
at full size. Offered to Casting as the service "orbit" (`manifest.start`): Casting never imports this module.

`orbit_pick(ctx)` is the model: the pulldown's model when it is a present Ref2VA video model (its pictures are
identities, `models.identities`), else the last video model picked (`lastModel`) when it is one, else the only present
one; else one line. The pulldown and `lastModel` are read, never set. `orbit_plan(ctx, pictures, prompt, seed)` is the
job: one `ClipRequest` built here, not by `build.clip_job` (the press reads the session's boxes and judges); the
pictures are identities in box order, each `cast.identity` (no views: `cast.identities` adds a character's
`<Name>.<view>.*`), no more than the model's own cap (`picture_refs(model)["max"]`, not the bar's 3); `ORBIT` frames (or
the caller's) on the model's lattice; the model's 9:16 size nearest `PORTRAIT` (people stand: portrait); steps, LoRAs
and text encoder from Generate's card for that model, as a clip press takes them; no judge, sound, video, voices or
reference detail. Then a frames request (`FramesRequest`) takes `VIEWS` (or the caller's) from the clip the first step
made, which lands in Media as it is made ("kept").
"""
from __future__ import annotations

import os
import posixpath
from typing import Any

from hub.core.api import ClipRequest, Ctx, FramesRequest, Invalid, JobPlan, clip_facts, request_wire, whole

from . import build, cast, models, routes, screen

NO_REF2VA = "Pick a Ref2VA video model in Generate (one that takes reference pictures)"
ORBIT = 124                                  # the 6-panel workflow's length (R51)
VIEWS = (2, 21, 42, 63, 84, 113)             # front, left, back, right, face, three-quarter face (R51, nodes 200-205)
PORTRAIT = (704, 1280)                       # 9:16, the size the 9:16 tier nearest it is picked by
STEP_NAMES = ["Orbit", "Views"]
NO_PICTURE = "Put the character's picture in box 1"
NO_PORTRAIT = "{} makes no 9:16 clip"
OUTSIDE = "The views must lie inside the orbit"


def _ref2va(model: dict[str, Any] | None, present: list[dict[str, Any]]) -> bool:
    return model is not None and model in present and models.identities(model)


def orbit_pick(ctx: Ctx) -> dict[str, Any]:
    """The Ref2VA video model the orbit runs on (the module docstring); else `NO_REF2VA`. Only read."""
    cat = models.cached()
    if cat is None:
        raise Invalid("model", NO_REF2VA)
    present = models.present(cat)
    saved = ctx.doc(routes.DRAFT, {}).get()
    last = saved.get("lastModel") if isinstance(saved.get("lastModel"), dict) else {}
    for model in (models.find(cat, saved.get("model")), models.find(cat, last.get("video"))):
        if _ref2va(model, present):
            return model                                         # type: ignore[return-value]
    every = [m for m in present if models.identities(m)]
    if len(every) == 1:
        return every[0]
    raise Invalid("model", NO_REF2VA)


def portrait(model: dict[str, Any], facts: dict[str, Any]) -> tuple[int, int]:
    """The model's 9:16 size nearest `PORTRAIT` in pixels, of every tier it has, within its budget; else one line."""
    top = models.budget(model)
    sizes = [(int(s[0]), int(s[1])) for t in facts["tiers"] if (s := t["sizes"].get("9:16"))]
    sizes = [s for s in sizes if top is None or s[0] * s[1] <= top]
    if not sizes:
        raise Invalid("model", NO_PORTRAIT.format(model["name"]))
    want = PORTRAIT[0] * PORTRAIT[1]
    return min(sizes, key=lambda s: (abs(s[0] * s[1] - want), s))


def _views(views: Any, frames: int) -> tuple[int, ...]:
    """The frames to take: a non-empty, strictly rising run of whole numbers inside the orbit; else one line."""
    if not isinstance(views, (list, tuple)) or not views or not all(
            isinstance(v, int) and not isinstance(v, bool) for v in views):
        raise Invalid("views", OUTSIDE)
    if views[0] < 0 or views[-1] >= frames or any(a >= b for a, b in zip(views, views[1:], strict=False)):
        raise Invalid("views", OUTSIDE)
    return tuple(views)


def orbit_plan(ctx: Ctx, pictures: list[str], prompt: str, seed: int | None = None, frames: Any = ORBIT,
               views: Any = VIEWS) -> JobPlan:
    """The orbit's job: the clip, then its views (the module docstring). `pictures` are media ids in box order, box 1
    the character's picture; `frames` the clip's length (on the model's lattice) and `views` the frames taken from it
    (an extra's 107 and four). Every refusal is one line."""
    model = orbit_pick(ctx)
    label, facts = str(model["name"]), clip_facts(model)
    if facts is None:
        raise Invalid("model", NO_REF2VA)
    cap = int((models.picture_refs(model) or {}).get("max") or 0)
    if not isinstance(pictures, list) or not pictures:
        raise Invalid("pictures", NO_PICTURE)
    if len(pictures) > cap:
        raise Invalid("pictures", f"{label} takes {cap} pictures; this cast has {len(pictures)}")
    refs = [cast.identity(n, cast.image(ctx, item, "pictures"), False, None, model, label)
            for n, item in enumerate(pictures, 1)]
    if not isinstance(prompt, str) or not prompt.strip():
        raise Invalid("prompt", "Write a prompt")
    if seed is not None:                         # None sends none, the engine's own
        seed = whole(seed, "seed", 0, screen.SEED_MAX, f"Seed must be 0 to {screen.SEED_MAX:,}")
    width, height = portrait(model, facts)
    frames = models.frames(facts, frames)
    taken = _views(views, frames)
    card = screen.read(ctx)
    lo, hi = model.get("steps_range") or screen.STEPS
    steps = build._steps((card["advanced"].get(model["id"]) or {}).get("steps"), model, label, facts["steps"], lo, hi)
    loras = build._loras(model, screen.stack(card, model["id"]))
    clip = request_wire(ClipRequest(
        model["id"], prompt, (width, height), seed, frames, steps=steps, loras=[(name, s) for _, name, s in loras],
        references=refs, encoder=screen.clip_encoder(card, model)))
    views = request_wire(FramesRequest("", taken))
    summary = {
        "prompt": prompt, "model": label, "model_id": model["id"], "mode": "refs", "kind": "clip", "width": width,
        "height": height, "count": 1, "frames": frames, "seconds": round(frames / facts["fps"], 2), "steps": steps,
        "guidance": None, "seeds": [] if seed is None else [seed], "step_names": list(STEP_NAMES),
        "loras": [{"id": i, "name": os.path.splitext(posixpath.basename(n))[0], "strength": s} for i, n, s in loras],
    }
    return JobPlan("image", model["id"], (clip, views), summary, inputs=({}, {"clip": (1, "kept")}))
