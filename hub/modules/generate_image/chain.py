"""Continue a clip: box 1 holds a clip, and the engine makes its scene longer (R7 §2.1).

The engine decodes the whole source and writes the source plus the new frames as one file. The one request names the
clip as its `source` (an absolute real path) and the new part as N frames (the Seconds setting), at the source's size;
the adapter runs it in one pass of N + overlap - 1 frames, never more than the engine's largest window (the catalog's
`video.window_max`, else the frame maximum); the scene grows by N - 1 frames. The overlap and the frame lattice are
the catalog's (`video.overlap`, `video.frames`), never literals here.

Clips are temporary files: a continued clip lands in `clips/<day>/<time>.mp4` like any clip, and its source stays
where it is (no folder per scene). Continuing one clip twice makes two clips (a branch).

On a model whose boxes are identities (Ref2VA, `models.identities`), boxes 2.. beside the clip hold the character
pictures placed there, up to the model's `references.max`; they go with the clip exactly as a fresh clip's
identities go (the engine's native continue keeps only the overlap frames, its pipeline.py:812-813 upstream).
Any other model: box 1 alone.

Memory only, the session's (like `last_seeds`): `last_clip`, the clip this screen made last, its best take when the
job judged several (`on_job_finished`). A
placed clip goes to the model in Generate's pulldown, when it continues one; else it is refused.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from starlette.requests import Request

from hub.core.api import ClipRequest, Ctx, Invalid, JobPlan, Reference, request_wire

from . import cast, models, routes, screen, takes

GONE = "The clip to continue is gone"
CANNOT = "{} cannot continue a clip"
ONLY_BOX_1 = "A continued clip takes only box 1"
IDENTITIES = "A continued clip takes at most {} identities on {}"
STEP_MAX = "Each step is at most {:.1f} s"
UNREADABLE = "This clip is not an MP4 the hub can read"
SHORT = "This clip is shorter than {} frames"
SIZE = "This clip's size is not one the model makes"
SCENE = "The scene would be {:g} s; the longest is {} s"
FIELD = "references"


def is_clip(ctx: Ctx, item: Any) -> bool:
    return isinstance(item, str) and ctx.files.kind(item) == "clip"


def beside(refs: Any) -> list[Any]:
    """The boxes after a clip in box 1 (the boxes as a job sends them): [] when they are all empty."""
    return list(refs[1:]) if isinstance(refs, list) and any(refs[1:]) else []


def source(ctx: Ctx, refs: Any, model: dict | None = None) -> str | None:
    """Box 1's clip id (the boxes as a job sends them), or None when no box holds a clip. A clip in box 2 or 3 is
    refused; so is anything in boxes 2.. beside a clip, unless `model` takes identities: then up to its maximum."""
    refs = refs if isinstance(refs, list) else []
    at = [k for k, item in enumerate(refs) if is_clip(ctx, item)]
    if not at:
        return None
    rest = beside(refs)
    if at != [0] or (rest and not (model and models.identities(model))):
        raise Invalid(FIELD, ONLY_BOX_1)
    top = int((models.picture_refs(model) or {}).get("max") or 0) if rest and model else 0
    if len(rest) > top:
        raise Invalid(FIELD, IDENTITIES.format(top, model["name"] if model else ""))
    return str(refs[0])


def held(ctx: Ctx) -> dict | None:
    """The session's box 1 when it holds a clip ({id, w, h, kind, seconds}), else None."""
    refs = routes.session_part(ctx).get("references")
    first = refs[0] if isinstance(refs, list) and refs else None
    return first if isinstance(first, dict) and is_clip(ctx, first.get("id")) else None


def last_clip(ctx: Ctx) -> str:
    value = routes.session_part(ctx).get("last_clip")
    return value if isinstance(value, str) else ""


def overlap(model: dict) -> int | None:
    """The overlap the model continues with (the catalog's), None when it cannot continue a clip."""
    clip = models.video(model)
    value = clip.get("overlap") if clip and clip.get("continues") else None
    return value if isinstance(value, int) and value > 1 else None


def facts(ctx: Ctx, clip_id: Any) -> dict[str, Any]:
    """The clip's facts ({w, h, fps, frames, seconds, audio}): refused when it is gone or does not read."""
    try:
        ctx.files.existing_media(clip_id)
    except Invalid:
        raise Invalid(FIELD, GONE) from None
    if not is_clip(ctx, clip_id):
        raise Invalid(FIELD, GONE)
    seen = ctx.files.clip_facts(clip_id)
    if seen is None:
        raise Invalid(FIELD, UNREADABLE)
    return seen


def check(ctx: Ctx, model: dict, clip_id: Any) -> tuple[dict[str, Any], int]:
    """A clip this model can continue: its facts and the model's overlap; else one plain line. The size must be one
    of the model's own (any tier the catalog reports for it): the engine follows the source's size."""
    seen = facts(ctx, clip_id)
    over = overlap(model)
    if over is None:
        raise Invalid(FIELD, CANNOT.format(model["name"]))
    if seen["frames"] < over:
        raise Invalid(FIELD, SHORT.format(over))
    sizes = {tuple(s) for t in (model.get("video") or {}).get("tiers") or [] for s in t["sizes"].values()}
    if (seen["w"], seen["h"]) not in sizes:
        raise Invalid(FIELD, SIZE)
    return seen, over


def _cap(ctx: Ctx, scene: float, reached: bool) -> None:
    """The scene-length cap (`continue_max_seconds`): a scene above it, or (`reached`) at it, is refused."""
    cap = ctx.settings.get("continue_max_seconds")
    if isinstance(cap, int) and (scene >= cap if reached else scene > cap):
        raise Invalid(FIELD, SCENE.format(round(scene, 2), cap))


def box(ctx: Ctx, model: dict, clip_id: str) -> dict[str, Any]:
    """Box 1 for a clip placed for this model: {id, w, h, kind: "clip", seconds}; its own length under the cap."""
    seen, _ = check(ctx, model, clip_id)
    _cap(ctx, seen["seconds"], True)
    return {"id": clip_id, "w": seen["w"], "h": seen["h"], "kind": "clip", "seconds": seen["seconds"]}


def plan(ctx: Ctx, p: dict, model: dict, ui: dict, checked: dict) -> JobPlan:
    """The continue of box 1's clip, with the identities beside it (`source`): the values `build.clip_job` checked
    (`prompt`, `frames`, `steps`, `seed`, `encoder`, `loras`: (name, strength) pairs, `named`: their summary), the
    clip's checks, then the one request."""
    clip_id = str(p["references"][0])
    seen, over = check(ctx, model, clip_id)
    video, n = ui["video"], checked["frames"]
    fps, top = video["fps"], video.get("window_max") or video["frames"]["max"]   # one pass: at most the largest window
    if n + over - 1 > top:
        raise Invalid("frames", STEP_MAX.format((top - over + 1) / fps))
    scene = round(seen["seconds"] + (n - 1) / fps, 2)
    _cap(ctx, scene, False)
    path = str(Path(ctx.files.resolve(clip_id)).resolve())
    rest, cut = beside(p["references"]), p.get("cutout") or []
    boxes = [(str(r), cast.image(ctx, r, FIELD), k < len(cut) and bool(cut[k])) for k, r in enumerate(rest, 1)]
    top = int((models.picture_refs(model) or {}).get("max") or 0) or len(boxes)
    who = cast.identities(ctx, boxes, top, model, ui["label"])               # as a fresh clip's, views and all
    task = request_wire(ClipRequest(
        model["id"], checked["prompt"], (seen["w"], seen["h"]), checked["seed"], n, steps=checked["steps"],
        loras=checked["loras"], references=[Reference(path, "source"), *who], encoder=checked["encoder"],
        **takes.judging(ctx)))
    summary = {
        "prompt": checked["prompt"], "model": ui["label"], "model_id": model["id"], "mode": "continue",
        "kind": "clip", "continues": clip_id, "width": seen["w"], "height": seen["h"], "count": 1, "frames": n,
        "seconds": round((n - 1) / fps, 2), "scene_seconds": scene, "steps": checked["steps"], "guidance": None,
        "seeds": [checked["seed"]], "loras": checked["named"],
        "references": [PurePosixPath(clip_id).stem, *(cast.label(ctx, {"id": r}) for r in rest)]}
    return JobPlan("image", model["id"], (task,), summary)


async def continue_clip(ctx: Ctx, request: Request) -> dict:
    """POST /continue {id}: the clip into box 1 of the pulldown's model, when it continues a clip (Media's
    Continue, a clip dropped on a box); else refused in one line. The model is never changed; open Generate windows
    redraw. -> {id, model, label}."""
    body = routes._body(await request.body(), "clip")
    clip_id = body.get("id")
    facts(ctx, clip_id)
    try:
        cat = await models.catalog(ctx)
    except Exception as exc:
        raise Invalid("engine", models.reason(exc)) from None
    model = screen.pick_model(cat, screen.read(ctx))
    item = box(ctx, model, clip_id)
    routes.session_part(ctx)["references"] = [item]
    ctx.bus.publish("changed", "draft", {})
    return {"id": item["id"], "model": model["id"], "label": model["name"]}


async def on_job_finished(ctx: Ctx, data: dict) -> None:
    """A finished Generate job that made clips: `last_clip` is the take it marked best (`notes.best`),
    else the newest. Then the press's `last_take` and a line's pace (`takes`): read from the
    job's notes, memory only; nothing is submitted from here."""
    if data.get("state") != "done" or data.get("tool") != ctx.module_id:
        return
    made = [o for o in data.get("outputs") or [] if is_clip(ctx, o)]
    best = (data.get("notes") or {}).get("best")
    if made:
        routes.session_part(ctx)["last_clip"] = best if best in made else made[-1]
    job = ctx.jobs.get(str(data.get("job")))
    if job is not None and job.plan.summary.get("kind") == "sound":
        await takes.on_finished(ctx, job, data)                # the best take, the pace
    elif job is not None and job.plan.summary.get("kind") == "clip":
        await takes.on_clip_finished(ctx, job, data)           # the best take
