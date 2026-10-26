"""One Generate press -> a JobPlan of N picture requests, or of one clip request for a video
model (`clip_job`), or of one spoken line for a speech model (`speech.speech_job`). Every sent value is explicit:
Generate's random seeds are drawn here (a job of the Hub's own with `"none"` sends none), model
defaults fill steps and guidance, image paths are absolute and LoRA names are the engine's own. A request speaks the
Hub's words (`api.PictureRequest`, `api.ClipRequest`): its pictures carry their role (a picture model's `reference`;
a clip's `start` and `end` frames or its `identity` pictures). The worker's adapter turns it into its engine's
task."""
from __future__ import annotations

import os
import posixpath
from typing import Any

from hub.core.api import (
    ClipRequest,
    Ctx,
    Invalid,
    JobPlan,
    PictureRequest,
    Reference,
    number,
    request_wire,
    seeds,
    whole,
)

from . import cast, chain, clipconvert, clipsound, clipvideo, clipvoice, models, prerun, routes, screen, speech, takes

MODE_TEXT = {"new": "{} needs a reference image", "refs": "{} can't use reference images"}
NEEDS_IDENTITY = "{} needs at least one image reference"   # the engine's manifest check, said before submit
# A start frame: box 1's picture opens the clip, cropped to the clip's canvas so the clip is the size asked for (the
# worker's adapter does the crop as its engine line does). On a model whose catalog facts say `end`, box 2's picture
# closes it, cropped the same way.
LAST_ALONE = "A last frame needs a start frame in box 1"
MIXED_CUTOUT = "Cut-out is on or off for every box on {}"     # a line with one switch for every identity (`cutout`)
OVER_BUDGET = "{}×{} is more than {} makes ({:,} pixels at most)"


_int, _number = whole, number                              # the core's plain-value checks (`api.whole`, `api.number`)


def _seeds(spec: Any, count: int) -> list[int | None]:
    """Generate's "random" (drawn here) and "fixed" (the value, then + 1 for each next); "none" (set only by the Hub's
    own jobs, never by a press) is no seed: `[None] * count`, the engine's own default."""
    if isinstance(spec, dict) and spec.get("mode") == "none":
        return [None] * count
    if not isinstance(spec, dict) or spec.get("mode") not in ("random", "fixed"):
        raise Invalid("seed", "Choose a random or fixed seed")
    first = None if spec["mode"] == "random" else _int(spec.get("value"), "seed", 0, screen.SEED_MAX,
                                                       f"Seed must be 0 to {screen.SEED_MAX:,}")
    return seeds(first, count, screen.SEED_MAX)


def _images(ctx: Ctx, p: dict, mode: str, cap: int) -> list[Reference]:
    """The reference pictures (absolute paths, box order); the adapter sends them as the model takes them."""
    refs = p.get("references") or []
    if not isinstance(refs, list):
        raise Invalid("references", "References must be a list")
    if mode == "new":
        return []
    if not refs:
        raise Invalid("references", "Add at least one reference")
    if len(refs) > cap:
        raise Invalid("references", f"Too many references for this model ({len(refs)} of {cap})")
    return [Reference(cast.image(ctx, r, "references"), "reference") for r in refs]


def _loras(model: dict, value: Any) -> list[tuple[str, str, float]]:
    """[(id, engine name, strength)] for LoRAs above 0, in stack order."""
    if not isinstance(value, list):
        raise Invalid("loras", "LoRAs must be a list")
    out = []
    for entry in value:
        if not isinstance(entry, dict):
            raise Invalid("loras", "Each LoRA needs an id and a strength")
        lo, hi = screen.STRENGTH
        strength = round(_number(entry.get("strength"), "loras", lo, hi, f"LoRA strength must be {lo} to {hi}"), 2)
        if strength == 0:
            continue
        name = models.lora_name(model, entry.get("id"))
        if name is None:
            raise Invalid("loras", f"LoRA \"{entry.get('id')}\" was not found for this model")
        out.append((str(entry["id"]), name, strength))
    return out


def _prompt(p: dict) -> str:
    prompt = p.get("prompt") if isinstance(p.get("prompt"), str) else ""
    if not prompt.strip():
        raise Invalid("prompt", "Write a prompt")
    return prompt


def _clip_refs(ctx: Ctx, p: dict, ui: dict) -> list[str]:
    """A clip's pictures (absolute paths, box order), the modes as for a picture: "new" sends none, "refs" the
    boxes, up to the model's cap. A model that needs one (identities) is refused with none, in the engine's sense."""
    mode, refs = p.get("mode"), p.get("references") or []
    if not isinstance(refs, list):
        raise Invalid("references", "References must be a list")
    if mode not in ("new", "refs"):
        raise Invalid("mode", "Choose New or References")
    if "new" not in ui["modes"] and (mode == "new" or not refs):
        raise Invalid("references", NEEDS_IDENTITY.format(ui["label"]))
    if mode not in ui["modes"]:
        raise Invalid("mode", MODE_TEXT[mode].format(ui["label"]))
    if mode == "new":
        return []
    if not refs:
        raise Invalid("references", "Add at least one reference")
    if len(refs) > ui["refCap"]:
        raise Invalid("references", f"Too many references for this model ({len(refs)} of {ui['refCap']})")
    if not refs[0] and any(refs[1:]) and (ui["video"].get("references") or {}).get("role") == "start":
        raise Invalid("references", LAST_ALONE)                # the boxes are dense: box 2 never stands alone
    return [cast.image(ctx, r, "references") for r in refs]


def _cutout(p: dict, model: dict, label: str, skip: int = 0) -> list[bool]:
    """The boxes' cut-out flags (`cutout`, one per entry of `references`, in box order; [] when absent), checked: a
    true on a model whose boxes are not identities is refused (the engine honours it for identities alone), and so
    is a mix of on and off where the engine has one switch for every box (the catalog's `cutout` "all"); the first
    `skip` boxes (a continued clip's) are not counted in the mix."""
    value, refs = p.get("cutout"), p.get("references")
    if value is None:
        return []
    count = len(refs) if isinstance(refs, list) else 0
    if not isinstance(value, list) or len(value) > count or any(not isinstance(v, bool) for v in value):
        raise Invalid("cutout", "Cut-out must be on or off for each box")
    if any(value) and not models.identities(model):
        raise Invalid("cutout", f"{label} cuts out no backgrounds")
    every = [n < len(value) and value[n] for n in range(skip, count)]
    if any(every) and not all(every) and (models.picture_refs(model) or {}).get("cutout") == "all":
        raise Invalid("cutout", MIXED_CUTOUT.format(label))
    return value


def _steps(value: Any, model: dict, label: str, default: int, lo: int, hi: int) -> int:
    """The steps a job runs: `value` (the model's default when None) within lo..hi; a model whose steps are locked
    (`models.locked_steps`) runs its own, and another value is refused in one line."""
    models.check_steps(model, label, value)
    if (locked := models.locked_steps(model)) is not None:
        return locked
    return default if value is None else _int(value, "steps", lo, hi, f"Steps must be {lo} to {hi}")


def _within(model: dict, label: str, width: int, height: int) -> None:
    """A size the engine takes for this model: no more pixels than its budget (`models.budget`)."""
    top = models.budget(model)
    if top is not None and width * height > top:
        raise Invalid("width", OVER_BUDGET.format(width, height, label, top))


def _clip_pictures(ctx: Ctx, p: dict, model: dict, label: str, paths: list[str]) -> list[Reference]:
    """A clip's pictures by role: box 1 as the start frame and box 2 as the last frame, or every box as an identity
    (`cast.identities`)."""
    refs = models.picture_refs(model)
    if not paths or refs is None:
        return []
    if models.identities(model):
        cut = _cutout(p, model, label)
        boxes = [(item_id, path, n <= len(cut) and cut[n - 1])
                 for n, (item_id, path) in enumerate(zip(p["references"], paths, strict=True), 1)]
        cap = int((refs.get("max") or 0) or len(boxes))
        return cast.identities(ctx, boxes, cap, model, label)
    if len(paths) > 1 and refs.get("end"):
        return [Reference(paths[0], "start"), Reference(paths[1], "end")]
    return [Reference(paths[0], "start")]


def clip_job(p: dict, ctx: Ctx, model: dict, ui: dict) -> JobPlan:
    """One clip: one request in one pass, every value checked here (the engine's own refusal is one vague line).
    The count is always 1; the size is one of the offered tiers; the length is on the lattice; the pictures are the
    model's role's (`_clip_pictures`). One pass: the adapter keeps the window to the whole clip. A clip in box 1 is
    continued (`chain.plan`): its size and boxes are the clip's, the rest is checked here as for any clip."""
    clip = ui["video"]
    held = chain.source(ctx, p.get("references"), model)
    heard = clipsound.sound(ctx, p, ui, bool(held))        # a sound the clip follows, else None
    shown = clipvideo.video(ctx, p, ui, bool(held))        # a reference video for camera and set
    paths = [] if held else _clip_refs(ctx, p, ui)
    prompt = _prompt(p)
    size = [p.get("width"), p.get("height")]
    if not held and not any(size == list(s) for t in clip["tiers"] for s in t["sizes"].values()):
        raise Invalid("width", "Choose a size the model can make")
    if not held:
        _within(model, ui["label"], size[0], size[1])
    f, raw = clip["frames"], p.get("frames")
    if heard:                                              # the clip is the sound's length
        frames = clipsound.frames(clip, heard[1])
    elif raw is None:
        frames = screen.clip_frames(screen.read(ctx), model)
    else:
        frames = models.frames(clip, _int(raw, "frames", f["min"], f["max"], f"Choose {f['min']} to {f['max']} frames"))
    lo, hi = model.get("steps_range") or screen.STEPS
    steps = _int(_steps(p.get("steps"), model, ui["label"], clip["steps"], lo, hi), "steps", lo, hi,
                 f"Steps must be {lo} to {hi}")
    loras = _loras(model, p.get("loras") or [])
    seed = _seeds(p.get("seed"), 1)[0]
    card = screen.read(ctx)
    encoder = screen.clip_encoder(card, model)             # the card's text encoder, else None: the model's default
    detail = screen.clip_detail(card, model)               # the card's detail, else None: the factory default
    named = [{"id": i, "name": os.path.splitext(posixpath.basename(n))[0], "strength": s} for i, n, s in loras]
    pairs = [(name, s) for _, name, s in loras]
    if held:
        return chain.plan(ctx, p, model, ui, {"prompt": prompt, "frames": frames, "steps": steps, "seed": seed,
                                              "encoder": encoder, "loras": pairs, "named": named})
    refs = _clip_pictures(ctx, p, model, ui["label"], paths)
    spoken = clipvoice.voices(ctx, model, ui, bool(heard), len(refs))  # the speakers' samples as audio references
    task = request_wire(ClipRequest(
        model["id"], prompt, (size[0], size[1]), seed, frames, steps=steps, loras=pairs, references=refs,
        encoder=encoder, detail=detail, sound=heard[0] if heard else None, sound_seconds=heard[1] if heard else None,
        video=shown[0] if shown else None, video_seconds=shown[1] if shown else None, voices=spoken,
        **takes.judging(ctx, refs)))
    summary = {
        "prompt": prompt, "model": ui["label"], "model_id": model["id"], "mode": "refs" if paths else "new",
        "kind": "clip", "width": size[0], "height": size[1], "count": 1, "frames": frames,
        "seconds": round(frames / clip["fps"], 2), "steps": steps, "guidance": None,
        "seeds": [seed] if seed is not None else [], "loras": named,
        "references": [cast.label(ctx, {"id": r}) for r in p["references"]] if paths else [],
        **({"sound": heard[2]} if heard else {}), **({"video": shown[2]} if shown else {}), **takes.asked(ctx),
    }
    return clipconvert.plan(ctx, model, ui, task, summary, bool(heard))     # + the speaker's voice by SeedVC


def image_job(params: dict, ctx: Ctx) -> JobPlan:
    """The Generate press: a line (`speech`), a clip (`clip_job`) or pictures (`picture_job`). The seeds it drew
    become the screen's `last_seeds` in `on_submitted`, for a press of this module's own or a screen's alone."""
    p = params if isinstance(params, dict) else {}
    if {"direct", "scene", "redo"} & p.keys():             # one request the Hub plans itself
        from . import director, redo, scene  # late: they build the press with this module
        return director.job(p, ctx) if "direct" in p else scene.job(p, ctx) if "scene" in p else redo.job(p, ctx)
    model = models.find(models.cached(), p.get("model"))
    if model is not None and model.get("why_not"):          # the engine has it; the Hub cannot drive it
        raise Invalid("model", str(model["why_not"]))
    if model is None or model["status"] == "missing":
        raise Invalid("model", "Choose a model")
    ui = models.ui_model(model, models.ref_caps(ctx))
    if ui["kind"] == "speech":                             # one line in one character's voice
        return speech.speech_job(p, ctx, model, ui, _prompt(p), _seeds(p.get("seed"), 1))   # takes: presstakes
    boxes = p.get("references") if isinstance(p.get("references"), list) else []
    _cutout(p, model, ui["label"], int(bool(boxes) and chain.is_clip(ctx, boxes[0])))   # a continued clip's box apart
    refs = p.get("references") if p.get("mode") == "refs" and isinstance(p.get("references"), list) else []
    if not ui["video"] and any(chain.is_clip(ctx, r) for r in refs):
        raise Invalid("references", chain.CANNOT.format(ui["label"]))      # a picture model takes no clip
    return clip_job(p, ctx, model, ui) if ui["video"] else picture_job(p, ctx, model, ui)


async def on_submitted(ctx: Ctx, data: dict) -> None:
    """`job.submitted`: a press keeps its seeds as `last_seeds` (memory only); a clip's job is planned by the engine
    before it runs (its error refuses it in one line). A job that plans itself is `director`'s."""
    job = ctx.jobs.get(data.get("job")) if data.get("kind") == f"{ctx.module_id}.image" else None
    if job is None or job.plan.prepare is not None:
        return
    if hasattr(job.plan.finish, "job") and job.plan.finish.job is None:   # a press's takes note their job
        job.plan.finish.job = job.id
    if data.get("by") in (ctx.module_id, "screen") and job.plan.summary.get("seeds"):   # seeds sent only
        summary = job.plan.summary
        routes.session_part(ctx)["last_seeds"] = {"model": summary["model_id"], "seeds": list(summary["seeds"])}
    planned = await prerun.engine_plan(ctx, job.plan)
    if planned is not None:
        ctx.jobs.note(job.id, plan=planned)
        if planned.get("errors"):
            ctx.jobs.refuse(job.id, str(planned["errors"][0]))
    await clipconvert.check(ctx, job)                      # SeedVC on and every file there


preflight = prerun.preflight                               # the same, for a plan not yet queued


def picture_job(p: dict, ctx: Ctx, model: dict, ui: dict) -> JobPlan:
    """N pictures, one engine task each, every value checked here."""
    label, mode = ui["label"], p.get("mode")
    if mode not in ("new", "refs"):
        raise Invalid("mode", "Choose New or References")
    if mode not in ui["modes"]:
        raise Invalid("mode", MODE_TEXT[mode].format(label))
    prompt = _prompt(p)
    block = model["block"]
    width = _int(p.get("width"), "width", 256, 4096, "Choose a size") // block * block
    height = _int(p.get("height"), "height", 256, 4096, "Choose a size") // block * block
    _within(model, label, width, height)
    count = _int(p.get("images"), "images", *screen.COUNT, f"Choose {screen.COUNT[0]} to {screen.COUNT[1]} images")
    steps = _steps(p.get("steps"), model, label, ui["defaults"]["steps"], *screen.STEPS)
    key, guidance = ui["guidanceKey"], None
    if key:
        raw = p.get("guidance")
        guidance = (ui["defaults"]["guidance"] if raw is None
                    else _number(raw, "guidance", *screen.GUIDANCE,
                                 f"Guidance must be {screen.GUIDANCE[0]} to {screen.GUIDANCE[1]}"))
    refs = _images(ctx, p, mode, ui["refCap"])
    loras = _loras(model, p.get("loras") or [])
    seeds = _seeds(p.get("seed"), count)
    summary = {
        "prompt": prompt, "model": label, "model_id": model["id"], "mode": mode, "width": width, "height": height,
        "count": count,
        "steps": steps, "guidance": guidance, "seeds": [s for s in seeds if s is not None],
        "loras": [{"id": i, "name": os.path.splitext(posixpath.basename(n))[0], "strength": s} for i, n, s in loras],
    }
    pairs = [(name, s) for _, name, s in loras]
    return JobPlan("image", model["id"], tuple(request_wire(PictureRequest(
        model["id"], prompt, (width, height), seed, steps=steps, guidance=guidance if key else None, loras=pairs,
        references=refs)) for seed in seeds), summary)
