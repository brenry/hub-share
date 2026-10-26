"""The drafts: per set name (case-folded), in memory, never on disk before Approve. A Hub
restart loses an unapproved draft (no log, CLAUDE.md).

A draft: `{name, mode: build|change|house|house-change, inputs: {pictures: [{id, keep}], description, pieces,
audience, house: {era, dress, hair, size}}, words, op, params, facts, seed, model, job, state, pan, plates, problem}`.
`params` is what its last job was sent but the seed (Again sends them on a new seed); `facts` the pan's {frames,
fps}. `state` is `none | rendering | ready | failed`. The job's end (`finished`, on `job.finished` of this module)
sets it from the job's outputs: one clip and one picture per grab is ready, the plates by grab order; anything else
failed with the job's line. A queued job cancelled now sends `job.finished` (cancelled); a rendering
draft whose job is gone without ending reads failed (`current`), kept as the fallback.

The two Prompt boxes (`box`, `set_box`), the stage pan's (`stage`: build and change) and the house pan's
(`house`: house and house change), `""` at start, held here only, never on disk, in a record or a log.
"""
from __future__ import annotations

import dataclasses
from typing import Any

from hub.core.api import Ctx, Invalid, JobPlan

from . import record

NOT_RUNNING = "Generate Image is not running"
TITLES = {"build": "Stage · {} · build", "change": "Stage · {} · change", "house": "House · {} · build",
          "house-change": "House · {} · change"}
CANCELLED = "The pan was cancelled"
NO_PLATES = "The pan made no plates"
HOUSE_WORDS = ("era", "dress", "hair", "size")
BOXES = ("stage", "house")
_drafts: dict[str, dict[str, Any]] = {}
_boxes = dict.fromkeys(BOXES, "")          # the Prompt boxes, never on disk


def box(which: str) -> str:
    return _boxes[which]


def boxes() -> dict[str, str]:
    return dict(_boxes)


def set_box(which: str, text: Any) -> str:
    """The box set as typed, byte for byte, when `text` is a string (else kept), whatever its length; -> the box."""
    if isinstance(text, str):
        _boxes[which] = text
    return _boxes[which]


def get(name: str) -> dict[str, Any] | None:
    return _drafts.get(name.casefold())


def put(draft: dict[str, Any]) -> dict[str, Any]:
    _drafts[draft["name"].casefold()] = draft
    return draft


def drop(name: str) -> dict[str, Any] | None:
    return _drafts.pop(name.casefold(), None)


def clear() -> None:
    _drafts.clear()
    _boxes.update(dict.fromkeys(BOXES, ""))


def every() -> list[dict[str, Any]]:
    return list(_drafts.values())


def by_job(job_id: Any) -> dict[str, Any] | None:
    return next((d for d in _drafts.values() if job_id is not None and d.get("job") == job_id), None)


def empty_inputs() -> dict[str, Any]:
    return {"pictures": [{"id": "", "keep": ""}], "description": "", "pieces": [],
            "audience": "seen", "house": {k: "" for k in HOUSE_WORDS}}


def record_inputs(name: str, approved: dict[str, Any]) -> dict[str, Any]:
    """The inputs as the approved record holds them (the input pictures as the set's own files)."""
    files = record.ids(name, approved)["pictures"]
    keeps = [str(p.get("keep") or "") for p in approved.get("pictures") or [] if isinstance(p, dict)]
    house = approved.get("house") if isinstance(approved.get("house"), dict) else {}
    return {"pictures": [{"id": f, "keep": k} for f, k in zip(files, keeps, strict=False)],
            "description": str(approved.get("description") or ""),
            "pieces": [str(e) for e in approved.get("elements") or []],
            "audience": approved.get("audience") if approved.get("audience") in record.AUDIENCES else "seen",
            "house": {k: str(house.get(k) or "") for k in HOUSE_WORDS}}


def fresh(name: str, inputs: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "mode": "build", "inputs": inputs, "words": None, "op": None, "params": None,
            "facts": None, "seed": None, "model": None, "job": None, "state": "none", "pan": None, "plates": None,
            "problem": None}


def busy(ctx: Ctx, draft: dict[str, Any] | None) -> bool:
    held = ctx.jobs.get(draft["job"]) if draft and draft.get("job") else None
    return held is not None and held.state in ("queued", "running")


def current(ctx: Ctx, name: str) -> dict[str, Any] | None:
    """The set's draft in memory, a rendering one whose job is gone read as failed; else None."""
    draft = get(name)
    if draft is not None and draft["state"] == "rendering" and ctx.jobs.get(draft["job"]) is None:
        draft.update(state="failed", problem=CANCELLED)
    return draft


def view(ctx: Ctx, draft: dict[str, Any]) -> dict[str, Any]:
    """The tab's `Draft` (routes docstring)."""
    plates = draft.get("plates")
    return {"mode": draft["mode"], "state": draft["state"], "job": draft.get("job"), "problem": draft.get("problem"),
            "model": draft.get("model"), "words": draft.get("words"), "pan": record.file(ctx, draft.get("pan")),
            "plates": {p: record.file(ctx, i) for p, i in plates.items()} if plates else None}


def summary(ctx: Ctx, name: str, held: dict[str, Any] | None, draft: dict[str, Any] | None) -> dict[str, Any]:
    """The tab's `Summary` (routes docstring)."""
    wide = record.ids(name, held)["plates"]["wide"] if held else None
    audience = (held or {}).get("audience") or (draft or {}).get("inputs", {}).get("audience") or "seen"
    return {"name": name, "approved": held is not None, "revision": held.get("revision") if held else None,
            "audience": audience, "house": bool(held and record.ids(name, held)["house"]),
            "thumb": ctx.files.thumb_url(wide) if wide else None, "state": draft["state"] if draft else "none"}


def job(params: dict, ctx: Ctx) -> JobPlan:
    """The `pan` job kind: Generate's pan (`ctx.service("pan")`), its card titled by mode (`TITLES`)."""
    try:
        plan_of = ctx.service("pan")
    except Invalid:
        raise Invalid("model", NOT_RUNNING) from None
    plan = plan_of(list(params.get("pictures") or []), params.get("prompt"), params.get("seed"),
                   params.get("length"), list(params.get("grabs") or []))
    title = TITLES.get(str(params.get("mode")), TITLES["build"]).format(params.get("name"))
    return dataclasses.replace(plan, summary={**plan.summary, "title": title})


def publish(ctx: Ctx, name: str, **extra: Any) -> None:
    ctx.bus.publish("changed", "changed", {"name": name, **extra})


async def finished(ctx: Ctx, data: dict) -> None:
    """`job.finished` of a pan: ready with one clip and its plates, else failed with the job's line."""
    draft = by_job(data.get("job")) if data.get("tool") == ctx.module_id else None
    if draft is None:
        return
    names = list(record.HOUSE if draft["mode"].startswith("house") else record.STAGE)
    outputs = [str(o) for o in data.get("outputs") or []]
    clips = [o for o in outputs if ctx.files.kind(o) == "clip"]
    images = [o for o in outputs if ctx.files.kind(o) == "image"]
    if data.get("state") == "done" and len(clips) == 1 and len(images) == len(names):
        draft.update(state="ready", pan=clips[0], plates=dict(zip(names, images, strict=True)), problem=None)
    else:
        job = ctx.jobs.get(str(data.get("job")))
        line = CANCELLED if data.get("state") == "cancelled" else getattr(job, "error", None) or NO_PLATES
        draft.update(state="failed", pan=clips[0] if clips else None, plates=None, problem=str(line))
    publish(ctx, draft["name"])
