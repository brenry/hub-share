"""Render: each shot's clip from Generate's `clip_plan` (a still first when needed), then the join;
`press(..., shot)`: that shot, then the join again (`reshot`). A shot: its camera, who is on (in the cards' order) with
each card's fields, the set, style, lines, cues, action and seconds; its pictures by the First cut's rule, or the shot's
own (`shotpics`). `Finish` files the cut (not for one shot alone) and each shot's clip in the clips."""
from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import Mapping
from typing import Any

from hub.core.api import Action, Canvas, Ctx, Duck, Invalid, JobPlan, JoinItem, JoinRequest, request_wire

from . import camera, reshot, routes, scripts, shotpics, videoloras
from .teach import SAY

KIND = "render"
GROUP = "Storyboard"
JOIN = (18, "medium")                    # Edit Video's join defaults (`sequence/join.py` CRF, PRESET)
NONE = "{} has no shot to render"
NOT_RUNNING = "Generate Image is not running"
BUSY = "{} is rendering"
LIVE = ("queued", "running")
running: dict[str, str] = {}             # script -> its Render job


def plain(e: Invalid) -> str:
    """A refusal's one line: the problem of a tool's `{problem, fix, hints}`, else its text."""
    try:
        got = json.loads(e.text)
    except ValueError:
        return e.text
    return str(got.get("problem") or e.text) if isinstance(got, dict) else e.text


def live(ctx: Ctx, name: str) -> str | None:
    """The script's Render job id while queued or running, else None (an ended one dropped)."""
    job = ctx.jobs.get(held) if (held := running.get(name)) else None
    if job is None or job.state not in LIVE:
        running.pop(name, None)
        return None
    return held


def cut(ctx: Ctx, name: str) -> str | None:
    """The last cut's media id when its file is there, else None."""
    held = ctx.doc("cuts", {}).get().get(name)
    if not isinstance(held, str):
        return None
    try:
        ctx.files.existing_media(held)
    except (Invalid, OSError, KeyError, ValueError):
        return None
    return held


def _words(*parts: Any) -> str:
    """The join: each field as written, a full stop after one with no closing mark, a space between."""
    return " ".join(t if t[-1] in ".!?…)" else t + "." for t in (" ".join(p.split()) for p in parts if isinstance(
        p, str) and p.strip()))


def _order(ev: dict) -> tuple[int, str]:
    """An event's place in time: its start, a sketch panel's `at_ms` (a panel has no `start_ms`)."""
    return ev.get("start_ms", ev.get("at_ms", 0)), str(ev.get("id"))


def who(scene: dict, shot: dict) -> list[str]:
    """Who is on, then each speaker of its lines not on (a line is spoken in frame)."""
    on = camera.in_frame(scene, shot)
    said = [str(ev.get("speaker")) for ev in sorted(shot["events"], key=_order) if ev.get("kind") == "line"]
    folded = {n.casefold() for n in on}
    return [*on, *dict.fromkeys(n for n in said if n.casefold() not in folded)]


def shot(script: dict, scene: dict, one: dict, people: list[str]) -> dict:
    """The `Clip:` route's shot of one Storyboard shot (the module docstring)."""
    context = script.get("context") or {}
    room = context.get("set") or {}
    looks = {str(m.get("name")).casefold(): _words(m.get("look"), m.get("costume")) for m in context.get("cast") or []}
    where = _words(room.get("name"), room.get("description"), *(room.get("elements") or []), *(  # the props as typed
        x for p in room.get("props") or [] if isinstance(p, dict) and p.get("name") for x in (p["name"],
                                                                                               p.get("description"))))
    events = sorted(one["events"], key=_order)
    cam = camera.of(one)
    out: dict[str, Any] = {
        "subjects": [{"name": n, **({"look": looks[n.casefold()]} if looks.get(n.casefold()) else {})}
                     for n in people],
        **({"where": where} if where else {}),            # an empty field sends nothing
        "camera": {k: cam[k] for k in ("framing", "move") if isinstance(cam.get(k), str)},
        "action": [one["action"]] if isinstance(one.get("action"), str) and one["action"].strip() else [],
        "lines": [{"speaker": ev["speaker"], "words": ev["words"],
                   **({"language": ev["language"]} if isinstance(ev.get("language"), str) else {})}
                  for ev in events if ev.get("kind") == "line"]}
    if isinstance(context.get("style"), str) and context["style"].strip():
        out["light"] = context["style"]
    room_sound = _words(*(ev.get("words") for ev in events if ev.get("kind") == "cue" and ev.get("cue") != "music"))
    music = _words(*(ev.get("words") for ev in events if ev.get("kind") == "cue" and ev.get("cue") == "music"))
    sound = {**({"ambience": room_sound} if room_sound else {}), **({"music": music} if music else {})}
    return {**out, **({"sound": sound} if sound else {})}


def pictures(ctx: Ctx, sid: str, people: list[str], cap: int, label: str) -> list[dict]:
    """The pictures of the listed people in frame, at most `cap` people, by the First cut's rule (`cast_pictures`),
    else each one's own picture; [] for nobody listed."""
    listed = {c["name"].casefold(): c for c in ctx.files.characters()}
    framed = [n for n in people if n.casefold() in listed][:max(1, cap)]
    if not framed:
        return []
    try:
        return list(ctx.service("cast_pictures")(sid, framed, max(1, cap), label))
    except Invalid:
        return [{"person": k, "name": listed[n.casefold()]["name"], "id": listed[n.casefold()]["id"]}
                for k, n in enumerate(framed)]


def uses(ctx: Ctx, script: dict, people: list[str]) -> dict[str, str]:
    """Each one in frame's `picture_use` (`storyclip.USES`) by name: the context's word when it is one and the member is
    listed in Characters; else "reference" when listed, "none" when not."""
    listed = {c["name"].casefold() for c in ctx.files.characters()}
    cast = {str(m.get("name")).casefold(): m for m in (script.get("context") or {}).get("cast") or []
            if isinstance(m, dict)}
    out = {}
    for n in people:
        said, pictured = (cast.get(n.casefold()) or {}).get("picture_use"), n.casefold() in listed
        out[n] = "none" if not pictured else said if said in ("reference", "frame", "none") else "reference"
    return out


def pictured(ctx: Ctx, sid: str, facts: dict, used: dict[str, str]) -> list[dict]:
    """The shot's pictures by its way (the module docstring)."""
    shown = [n for n, u in used.items() if u in ("reference", "frame")]
    if facts["way"] == "identity":
        return pictures(ctx, sid, shown, int(facts["cap"]), facts["label"])
    if facts["way"] == "start" and shown:
        first = [n for n in shown if used[n] == "frame"] or shown
        listed = {c["name"].casefold(): c for c in ctx.files.characters()}
        one = listed[first[0].casefold()]
        return [{"person": 0, "name": one["name"], "id": one["id"]}]
    return []


def plan(ctx: Ctx, name: Any, only: str | None = None) -> dict:
    """{name, parts, skipped}: every shot planned in order (`only`: that shot alone), each on its own model; one
    `Invalid` line when none can be."""
    name = scripts.name_of(name)
    if not scripts.exists(routes.folder(ctx), name):
        raise Invalid("name", f"There is no script named {name}")
    try:
        script = scripts.opened(routes.folder(ctx), name, routes.characters(ctx))
    except Invalid as e:
        raise Invalid("name", plain(e)) from None
    pairs = [(sc, s) for sc in script["scenes"] for s in sc["shots"] if only is None or str(s.get("id")) == only]
    if only is not None and not pairs:
        raise Invalid("shot", f"{name} has no shot {only}")
    if not pairs:
        raise Invalid("name", NONE.format(name))
    try:
        svc = ctx.service("clip_plan")()
    except Invalid:
        raise Invalid("render", NOT_RUNNING) from None
    svc.ready()
    parts, skipped, extra = [], [], videoloras.chosen(ctx)
    for k, (scene, one) in enumerate(pairs, 1):
        sid = str(one.get("id") or k)
        try:
            order = [str(m.get("name")).casefold() for m in (script.get("context") or {}).get("cast") or []]
            people = sorted(who(scene, one), key=lambda n: (order + [n.casefold()]).index(n.casefold()))  # cards' order
            used, own = uses(ctx, script, people), shotpics.get(ctx, name, sid)   # the shot's own pictures
            facts = svc.pick(sid, "reference" in used.values() or bool(own), "frame" in used.values())
            part = {"id": sid, "shot": shot(script, scene, one, people), "own": bool(own), "pictures": [
                {"person": k, "name": f"picture {k + 1}", "id": i} for k, i in enumerate(own)]
                or pictured(ctx, sid, facts, used),
                    "seconds": (one["end_ms"] - one["start_ms"]) / 1000, "model": facts["model"],
                    "way": facts["way"], "loras": extra}
            parts.append({**part, **svc.clip(part)})
        except Invalid as e:
            skipped.append(f"shot {sid} left out: {e.text}")
    if not parts:
        raise Invalid("render", skipped[0])
    order = [str(s.get("id") or k) for k, (_, s) in enumerate(
        ((sc, s) for sc in script["scenes"] for s in sc["shots"]), 1)]
    return {"name": name, "parts": parts, "skipped": skipped, "order": order}


def job(params: dict, ctx: Ctx) -> JobPlan:
    """The job: each planned shot's still (when it starts from one) and clip, then the join of the clips in order."""
    p = plan(ctx, (params or {}).get("script"), (params or {}).get("shot"))
    name, parts = p["name"], p["parts"]
    tasks: list[dict] = []
    inputs: list[dict] = []
    names: list[str] = []
    clips: list[int] = []
    for x in parts:
        if x.get("still"):
            tasks.append(x["still"])
            inputs.append({})
            names.append(f"Shot {x['id']} · first frame")
        inputs.append({"references.0.path": (len(tasks), "file")} if x.get("still") else {})
        tasks.append(x["task"])
        names.append(f"Shot {x['id']} · {x['seconds']:.1f} s")
        clips.append(len(tasks))
    first = parts[0]
    (w, h), fps = first["size"], float(first["fps"])
    items = [JoinItem("", 0, x["frames"], float(x["fps"]), x["size"][0], x["size"][1], x["frames"],
                      bool(x.get("audio"))) for x in parts]
    joined = JoinRequest(items, Canvas(w, h, fps), [], JOIN[0], JOIN[1], "mp4", Duck())
    seconds = round(sum(x["frames"] / float(x["fps"]) for x in parts), 2)
    summary = {"title": f"Render · {name} · {len(parts)} shots", "prompt": f"Render · {name}", "kind": "clip",
               "mode": "storyboard", "model": " + ".join(dict.fromkeys(x["label"] for x in parts)),
               "model_id": first["model"], "width": w, "height": h, "count": 1,
               "frames": sum(x["frames"] for x in parts), "seconds": seconds, "steps": first["steps"],
               "seeds": [x["task"]["seed"] for x in parts if x["task"].get("seed") is not None],   # sent
               "loras": first["loras"], "shots": len(parts), "step_names": [*names, f"Join · {seconds:.1f} s"]}
    whole = reshot.items(ctx, name, p["order"], first) if (params or {}).get("shot") else None
    if (params or {}).get("shot") and whole is None:     # one shot, another with no clip yet: its clip alone
        summary.update(title=f"Render · {name} · shot {first['id']}", step_names=names)
        return JobPlan("image", first["model"], tuple(tasks), summary, inputs=tuple(inputs),
                       finish=Finish(ctx, name, [first["id"]], p["skipped"], clips, cut=False))
    if whole is not None:                                # one shot, then the whole video joined again
        joined = JoinRequest(whole[0], Canvas(w, h, fps), [], JOIN[0], JOIN[1], "mp4", Duck())
        reshot.told(summary, name, first["id"], whole[0], names)
    fill = {f"items.{i}.path": (k, "kept") for i, k in enumerate(clips)} if whole is None else {
        f"items.{whole[1]}.path": (clips[0], "kept")}
    return JobPlan("image", first["model"], (*tasks, request_wire(joined)), summary, inputs=(*inputs, fill),
                   finish=Finish(ctx, name, [x["id"] for x in parts], p["skipped"], clips))


class Finish:
    """Any end: the landed cut filed and pointed at, each landed shot's clip filed beside it, the tab told."""

    def __init__(self, ctx: Ctx, name: str, ids: list[str], skipped: list[str], clips: list[int] | None = None,
                 cut: bool = True) -> None:
        self.ctx, self.name, self.ids, self.skipped, self.cut = ctx, name, ids, skipped, cut
        self.clips = clips or list(range(1, len(ids) + 1))     # each shot's clip task (a still's before it)

    def file(self, landed: Mapping[int, str]) -> str | None:
        files, made, cut, filed = self.ctx.files, None, (self.clips[-1] if self.clips else 0) + 1, {}
        if self.cut and landed.get(cut):
            with contextlib.suppress(Invalid, OSError):
                made = files.file_clip(landed[cut], GROUP, self.name)
        for k, sid in zip(self.clips, self.ids, strict=True):
            if landed.get(k):
                with contextlib.suppress(Invalid, OSError):
                    filed[sid] = files.file_clip(landed[k], GROUP, f"{self.name} {sid}")
        reshot.keep(self.ctx, self.name, filed)
        return made

    async def __call__(self, landed: Mapping[int, str]) -> None:
        made = await asyncio.to_thread(self.file, landed)
        if made is not None:
            self.ctx.doc("cuts", {}).patch({self.name: made})
        self.ctx.bus.publish("changed", "changed", {"name": self.name, "revision": time.time_ns() // 1000})


def press(ctx: Ctx, name: Any, shot: str | None = None) -> dict:
    """Render (`shot`: that shot alone): {job, shots, skipped} at once, or {problem} in one line (the queue's own
    refusals too)."""
    try:
        name = scripts.name_of(name)
    except Invalid as e:
        return {"problem": e.text}
    held = live(ctx, name)
    if held is not None:
        return {"problem": BUSY.format(name)}
    try:
        made = ctx.jobs.submit(KIND, {"script": name, **({"shot": str(shot)} if shot else {})})
    except Exception as exc:  # noqa: BLE001  (Invalid, or the queue's own refusal: its one line)
        said = str(getattr(exc, "text", None) or exc).strip().splitlines()
        return {"problem": said[0] if said else type(exc).__name__}
    running[name] = made.id
    fin = made.plan.finish
    ctx.bus.publish("changed", "changed", {"name": name, "revision": time.time_ns() // 1000})
    return {"job": made.id, "shots": len(fin.ids) if isinstance(fin, Finish) else 0,
            "skipped": list(fin.skipped) if isinstance(fin, Finish) else []}


def line(name: str, got: dict) -> str:
    """The chat's one line of a press."""
    if "problem" in got:
        return f"not rendered: {got['problem']}"
    left = f"; {'; '.join(got['skipped'])}" if got["skipped"] else ""
    return f"rendering {got['shots']} shot{'' if got['shots'] == 1 else 's'} into one video (job {got['job']}){left}"


async def script_render(ctx: Ctx, args: dict) -> dict:
    """The tool: Render on the open script; its one line."""
    from . import tools  # late: tools reads this module's neighbours

    try:
        name = tools._current(ctx)
    except Invalid as e:
        return {"script": None, "state": [f"not rendered: {plain(e)}"]}
    return {"script": name, "state": [line(name, press(ctx, name))]}


ACTION = Action("script_render", SAY["script_render"], {"type": "object", "additionalProperties": False,
                                                        "required": [], "properties": {}}, script_render)
