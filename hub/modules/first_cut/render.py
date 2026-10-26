"""The `first-cut.render` job: one clip per part not yet made, then one join with the whole mixed
track as its one sound; its finish files what landed and keeps the pointers.

`plan(ctx, name)` is the dry run (the Detail's `why` and part states): the script (`script.read`), Generate's service
(`first_cut`, else "Generate Image is not running"), its facts, the parts, every part's pictures, then every part's
slice (its path only) and request; nothing is written or submitted. `job` adds: slices older than a day removed, the
refusal when every part and the cut are current, the slices of the parts to render cut, and the plan: each rendered
part a take of its own (judged, never re-taken), the join's items trimmed to each part's `n` frames and silent, its
track 2 the track from `s0` to `E` at level 1, no duck; a reused part's item is its clip's real path, a rendered one's
is sent empty and filled as "kept". `Finish` (any end): each landed part filed `Clips/<day>/<Script> shots/<id>.mp4`,
the cut `Clips/<day>/First cut/<Script>.mp4`, the record written (`made`), this job's slices removed, the verdicts
read into memory (`routes.last`): a part's flag is its take's line when it does not pass.
"""
from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import Mapping
from typing import Any

from hub.core.api import (
    NO_MODEL,
    Canvas,
    Ctx,
    Duck,
    Invalid,
    JobPlan,
    JoinItem,
    JoinRequest,
    JoinSound,
    request_wire,
)

from . import made, parts, pictures, script, slices

KIND = "render"
JOIN = (18, "medium")                  # the scene join's crf and preset (`generate_image/scene.py`)
NOT_RUNNING = "Generate Image is not running"
CURRENT = "{}'s first cut is current: delete a shot's clip in Media to render it again"
SHOTS, CUTS = "{} shots", "First cut"   # the Clips groups: a script's parts, the cuts
UNFILED = "Its clip stayed where it landed in Clips: {}"
pending: dict[str, list[str]] = {}     # script -> the slices its last built job cut (`routes.press` clears them)


def service(ctx: Ctx) -> Any:
    try:
        return ctx.service("first_cut")()
    except Invalid:
        raise Invalid("first-cut", NOT_RUNNING) from None


def plan(ctx: Ctx, value: Any) -> dict[str, Any]:
    """The dry run: {name, read, svc, facts, parts, record, s0, end, cut_key}; each part with its pictures, slice,
    key, task, seconds, state (`made`, `changed`, `missing`) and recorded clip. Every refusal one `Invalid`."""
    got = script.read(ctx, value)
    name, body = got["name"], got["script"]
    svc = service(ctx)
    facts = svc.facts()
    every = parts.split(body, facts)
    for part in every:
        part["pictures"] = pictures.pick(ctx, part["shot"], part["who"], facts["cap"], facts["label"])
    context = body.get("context") if isinstance(body.get("context"), dict) else {}
    room = context.get("set") if isinstance(context.get("set"), dict) else {}
    look = {"set": {"name": room.get("name"), "elements": [e for e in room.get("elements") or []
                                                           if isinstance(e, str)]}, "style": context.get("style")}
    record = made.of(ctx, name)
    for part in every:
        part["slice"] = slices.where(ctx, got["track"], got["size"], got["mtime_ns"], part["start_ms"],
                                     part["render"], facts["fps"])
        digest = slices.digest(got["track"], part["slice"])
        part.update(svc.clip({**part, **look, "sound": str(part["slice"].path), "sound_digest": digest}))
        held = record["parts"].get(part["id"])
        part["state"] = "made" if held and held["key"] == part["key"] else "changed" if held else "missing"
        part["clip"] = held["clip"] if held else None
    s0, end = parts.span(body)
    base = (got["track"].name, got["size"], got["mtime_ns"], s0, end, facts["size"])
    stamps = [made.stamp(ctx, p["clip"]) if p["state"] == "made" else None for p in every]
    key = made.cut_key([p["key"] for p in every], stamps, *base) if all(stamps) else None
    return {"name": name, "read": got, "svc": svc, "facts": facts, "parts": every, "record": record, "s0": s0,
            "end": end, "cut_key": key, "base": base}


def step_name(part: dict, fps: float) -> str:
    """`Shot s2 · 8.0 s`, or `Shot s4 part 1 of 2 · 15.1 s`."""
    whose = f"Shot {part['shot']}" + (f" part {part['part']} of {part['of']}" if part["of"] > 1 else "")
    return f"{whose} · {part['n'] / fps:.1f} s"


def judged(part: dict) -> dict:
    """The part as the judges read a shot: its in-frame speakers (no words: a kept sound's are not judged), its
    framing."""
    speakers = list(dict.fromkeys(ln["speaker"] for ln in part["lines"] if ln["in_frame"]))
    framing = part["camera"].get("framing")
    return {"lines": [{"speaker": s} for s in speakers], "camera": {"framing": framing} if framing else {}}


def join(every: list[dict], paths: list[str], facts: dict, track: str, s0: float, end: float) -> JoinRequest:
    """The cut: each part trimmed to its own `n` frames and silent, the track from `s0` to `E` its one sound (track 2,
    level 1, no duck: `amix duration=first` keeps the pictures' length, the track's within half a frame)."""
    fps, (w, h) = float(facts["fps"]), facts["size"]
    items = [JoinItem(path, 0, x["n"], fps, w, h, x["render"], False) for x, path in zip(every, paths, strict=True)]
    return JoinRequest(items, Canvas(w, h, fps), [JoinSound(track, 0, round(s0), round(end), 1000.0)],
                       JOIN[0], JOIN[1], "mp4", Duck())


def job(params: dict, ctx: Ctx) -> JobPlan:
    """The job, or one `Invalid` line."""
    p = plan(ctx, (params or {}).get("script"))
    name, facts, got, every = p["name"], p["facts"], p["read"], p["parts"]
    slices.sweep(ctx)
    todo = [x for x in every if x["state"] != "made"]
    held_cut = p["record"]["cut"]
    if not todo and held_cut is not None and held_cut["key"] == p["cut_key"]:
        raise Invalid("first-cut", CURRENT.format(name))
    pending[name] = [str(x["slice"].path) for x in todo]    # removed by the press when the queue refuses the job
    for x in todo:
        slices.cut(got["track"], x["slice"])
    fps, (w, h) = facts["fps"], facts["size"]
    task_of = {x["id"]: k for k, x in enumerate(todo, 1)}
    fill = {f"items.{i}.path": (task_of[x["id"]], "kept") for i, x in enumerate(every) if x["id"] in task_of}
    paths = ["" if x["id"] in task_of else str(made.there(ctx, x["clip"])) for x in every]
    cut = join(every, paths, facts, os.path.realpath(got["track"]), p["s0"], p["end"])
    total = sum(x["n"] for x in every)
    takes = tuple(((k,),) for k in range(1, len(todo) + 1))
    summary = {"title": f"First cut · {name} · {len(every)} parts", "prompt": f"First cut · {name}",
               "model": facts["label"], "model_id": facts["model"], "kind": "clip", "mode": "first-cut",
               "width": w, "height": h, "count": 1, "frames": total, "seconds": round(total / fps, 2),
               "steps": facts["steps"], "loras": facts["loras"],
               "seeds": [x["task"]["seed"] for x in todo if x["task"].get("seed") is not None],
               "shots": len(todo), "step_names": [*(step_name(x, fps) for x in todo),
                                                  f"Join · {total / fps:.1f} s"]}
    finish = Finish(ctx, name, [(task_of[x["id"]], x["id"], x["key"], x["render"]) for x in todo], len(todo) + 1,
                    total, pending[name], len(every) - len(todo),
                    [(x["id"], x["key"], None if x["id"] in task_of else x["clip"]) for x in every], p["base"])
    return JobPlan("image", facts["model"] if todo else NO_MODEL, (*(x["task"] for x in todo), request_wire(cut)),
                   summary, inputs=(*({} for _ in todo), fill), finish=finish, takes=takes,
                   judge=p["svc"].judge([judged(x) for x in todo], takes) if todo else None)


class Finish:
    """At every end, what landed filed and pointed at; `job` is set by the press that submitted it. The cut is
    recorded only with every part's clip recorded; its key holds each part's clip id, size and mtime_ns, so a cut
    joined from an earlier take of a part is never current."""

    def __init__(self, ctx: Ctx, name: str, rendered: list[tuple[int, str, str, int]], join: int, frames: int,
                 used: list[str], reused: int, order: list[tuple[str, str, str | None]], base: tuple) -> None:
        self.ctx, self.name, self.rendered, self.join = ctx, name, rendered, join
        self.frames, self.used, self.reused, self.order, self.base = frames, used, reused, order, base
        self.job: str | None = None
        self.unfiled: dict[str, str] = {}             # part key -> why its clip could not be filed

    def file(self, landed: Mapping[int, str]) -> tuple[dict[str, dict], dict | None]:
        """The landed clips moved into their groups (in a thread): (parts, cut) for the record."""
        files, new = self.ctx.files, {}
        for k, pid, key, frames in self.rendered:
            if landed.get(k):
                try:
                    new[pid] = {"key": key, "clip": files.file_clip(landed[k], SHOTS.format(self.name), pid),
                                "frames": frames}
                except (Invalid, OSError) as e:
                    self.unfiled[key] = UNFILED.format(getattr(e, "text", None) or str(e) or type(e).__name__)
        cut = None
        clips = [new[pid]["clip"] if pid in new else reused for pid, _, reused in self.order]
        stamps = [made.stamp(self.ctx, c) for c in clips]
        if landed.get(self.join) and all(stamps):
            with contextlib.suppress(Invalid, OSError):
                cut = {"key": made.cut_key([key for _, key, _ in self.order], stamps, *self.base),
                       "clip": files.file_clip(landed[self.join], CUTS, self.name), "frames": self.frames}
        slices.remove(self.used)
        return new, cut

    async def __call__(self, landed: Mapping[int, str]) -> None:
        from . import routes  # late: routes reads this module

        new, cut = await asyncio.to_thread(self.file, landed)
        made.write(self.ctx, self.name, new, cut)
        job = self.ctx.jobs.get(self.job) if self.job else None
        verdicts = dict(getattr(job, "takes", None) or {})
        flags = routes.memory(self.name)["flags"]
        for _, pid, key, _ in self.rendered:            # a part filed now drops an earlier "not filed" flag
            if pid in new:
                flags.pop(key, None)
        for k, _, key, _ in self.rendered:
            take = verdicts.get(k)
            if take is not None and not take.passes:
                flags[key] = take.line
            elif take is not None:
                flags.pop(key, None)
        flags.update(self.unfiled)                    # a part that could not be filed says so on its row
