"""A set's pan: the Stage tab's one clip on a Ref2VA model, then its plates taken from it at full
size. Offered to the Stage module as the service "pan" (`manifest.start`): Stage never imports this module.

The orbit's route (`orbit.py`) with three differences: the length is the caller's, on the model's lattice; the size
is the model's 16:9 size nearest `WIDE` (`wide`: one plate serves 16:9 and, cut at its centre, 4:3); the frames
taken are the caller's `grabs`. The model is `orbit.orbit_pick` (the pulldown only read); the pictures
are identities in box order, each `cast.identity`, at most the model's own cap; steps, LoRAs and text encoder from
Generate's card for that model; no judge, sound, video, voices or reference detail. Then a frames request
(`FramesRequest`) takes `grabs` from the clip the first step made, which lands in Media as it is made ("kept").
"""
from __future__ import annotations

import os
import posixpath
from typing import Any

from hub.core.api import ClipRequest, Ctx, FramesRequest, Invalid, JobPlan, clip_facts, request_wire, whole

from . import build, cast, models, orbit, screen

WIDE = (864, 480)                            # 16:9 480p, the size the 16:9 tier nearest it is picked by
STEP_NAMES = ["Pan", "Plates"]
NO_PICTURE = "Put a picture of the set in box 1"
NO_WIDE = "{} makes no 16:9 clip"


def wide(model: dict[str, Any], facts: dict[str, Any]) -> tuple[int, int]:
    """The model's 16:9 size nearest `WIDE` in pixels, of every tier it has, within its budget; else one line."""
    top = models.budget(model)
    sizes = [(int(s[0]), int(s[1])) for t in facts["tiers"] if (s := t["sizes"].get("16:9"))]
    sizes = [s for s in sizes if top is None or s[0] * s[1] <= top]
    if not sizes:
        raise Invalid("model", NO_WIDE.format(model["name"]))
    want = WIDE[0] * WIDE[1]
    return min(sizes, key=lambda s: (abs(s[0] * s[1] - want), s))


def pan_plan(ctx: Ctx, pictures: list[str], prompt: str, seed: int | None, length: int, grabs: list[int]) -> JobPlan:
    """The pan's job: the clip, then its plates (the module docstring). `pictures` are media ids in box order;
    `grabs` 0-based frame indices, in the order the plates are wanted; every refusal is one line."""
    model = orbit.orbit_pick(ctx)
    label, facts = str(model["name"]), clip_facts(model)
    if facts is None:
        raise Invalid("model", orbit.NO_REF2VA)
    cap = int((models.picture_refs(model) or {}).get("max") or 0)
    if not isinstance(pictures, list) or not pictures:
        raise Invalid("pictures", NO_PICTURE)
    if len(pictures) > cap:
        raise Invalid("pictures", f"{label} takes {cap} pictures; this set has {len(pictures)}")
    refs = [cast.identity(n, cast.image(ctx, item, "pictures"), False, None, model, label)
            for n, item in enumerate(pictures, 1)]
    if not isinstance(prompt, str) or not prompt.strip():
        raise Invalid("prompt", "Write a prompt")
    if seed is not None:                         # None sends none, the engine's own
        seed = whole(seed, "seed", 0, screen.SEED_MAX, f"Seed must be 0 to {screen.SEED_MAX:,}")
    width, height = wide(model, facts)
    frames = models.frames(facts, length)
    card = screen.read(ctx)
    lo, hi = model.get("steps_range") or screen.STEPS
    steps = build._steps((card["advanced"].get(model["id"]) or {}).get("steps"), model, label, facts["steps"], lo, hi)
    loras = build._loras(model, screen.stack(card, model["id"]))
    clip = request_wire(ClipRequest(
        model["id"], prompt, (width, height), seed, frames, steps=steps, loras=[(name, s) for _, name, s in loras],
        references=refs, encoder=screen.clip_encoder(card, model)))
    plates = request_wire(FramesRequest("", tuple(int(g) for g in grabs)))
    summary = {
        "prompt": prompt, "model": label, "model_id": model["id"], "mode": "refs", "kind": "clip", "width": width,
        "height": height, "count": 1, "frames": frames, "fps": facts["fps"], "seconds": round(frames / facts["fps"], 2),
        "steps": steps, "guidance": None, "seeds": [] if seed is None else [seed], "step_names": list(STEP_NAMES),
        "loras": [{"id": i, "name": os.path.splitext(posixpath.basename(n))[0], "strength": s} for i, n, s in loras],
    }
    return JobPlan("image", model["id"], (clip, plates), summary, inputs=({}, {"clip": (1, "kept")}))
