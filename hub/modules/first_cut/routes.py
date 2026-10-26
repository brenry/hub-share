"""The First cut tab's routes, mounted at `/api/first-cut` (a paired screen only). The contract, which
the web builds to exactly:

    type Clip   = { id: string; url: string }
    type Cut    = { id: string; url: string; seconds: number }
    type State  = 'none' | 'queued' | 'running' | 'done' | 'failed' | 'cancelled'
    type Script = { name: string; seconds: number | null; shots: number | null; why: string | null;
                    state: State; job: string | null; cut: Cut | null }
    type Part   = { id: string; shot: string; part: number; of: number; start_ms: number; end_ms: number;
                    frames: number; render_frames: number; who: string[]; lines: number;
                    split: 'line' | 'window' | null; state: 'made' | 'changed' | 'missing';
                    clip: Clip | null; flag: string | null }
    type Detail = Script & { problem: string | null; parts: Part[] | null; order: string[] | null }
    GET  /api/first-cut/scripts        -> { scripts: Script[] }            by name
    GET  /api/first-cut/script?name=   -> Detail                           unknown name: 400 {field, text}
    POST /api/first-cut/render {name}  -> { job: string; render: number; reused: number } | { problem: string }
    bus  first-cut.changed {name}      on Render, and when its job ends

`state` is this session's last Render of the script (`none` before one; `queued`/`running` read from the job while it
runs); `job` its job's id; `cut` the record's cut when its file is there. `why` is the line that turns Render off:
in the listing the script's own (`script.read`), in the detail also the dry run's (the facts, the pictures, the slice,
the prompt); `parts` is
null when `why` is set. A part's `frames` is its own `n`, `render_frames` its `F`, `lines` how many lines it holds;
`state` `made` (recorded under its current key, the clip there), `changed` (a clip recorded under another key) or
`missing`; `clip` the recorded clip when there; `flag` its judges' line when its take was under the bar, or the line
saying its clip could not be filed (memory). Each part runs at most the model's `frames.max` frames (362 on H3
Ref2VA, ~15 s: MiniMax's one window and the director's `SHOT_MAX`), never the engine's longer `window_max`. `order` is
the running job's rendered part ids in task order (null when none runs), so `progress.index` maps to a part. `problem`
is the last Render's refusal or its job's error line. A refusal of Render is HTTP 200 `{problem}`, the queue's own
refusals (engine offline, queue full) passed as their one line. Memory only: `running`, `last` (a Hub
restart forgets them; the made parts and the cut stay).
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from starlette.requests import Request

from hub.core.api import Ctx, Invalid, Route

from . import made, render, script, slices

running: dict[str, str] = {}                       # script -> its Render's job
last: dict[str, dict[str, Any]] = {}               # script -> {state, problem, flags: {part key: line}}
BUSY = "{} is rendering"
LIVE = ("queued", "running")


def memory(name: str) -> dict[str, Any]:
    return last.setdefault(name, {"state": "none", "problem": None, "flags": {}})


def publish(ctx: Ctx, name: str) -> None:
    ctx.bus.publish("changed", "changed", {"name": name})


def live(ctx: Ctx, name: str) -> Any:
    """The script's Render job while it is queued or running, else None (a job gone or ended is dropped)."""
    held = running.get(name)
    job = ctx.jobs.get(held) if held else None
    if job is None or job.state not in LIVE:
        running.pop(name, None)
        return None
    return job


def _cut(ctx: Ctx, name: str, fallback: float | None) -> dict | None:
    cut = made.of(ctx, name)["cut"]
    if cut is None:
        return None
    facts = ctx.files.clip_facts(cut["clip"]) or {}
    seconds = facts.get("seconds") if isinstance(facts.get("seconds"), (int, float)) else fallback
    return {"id": cut["clip"], "url": ctx.files.url(cut["clip"]), "seconds": seconds}


def _script(ctx: Ctx, row: dict) -> dict:
    name, job = row["name"], live(ctx, row["name"])
    state = job.state if job is not None else memory(name)["state"]
    return {**row, "state": state, "job": job.id if job is not None else None, "cut": _cut(ctx, name, row["seconds"])}


def scripts(ctx: Ctx) -> dict:
    return {"scripts": [_script(ctx, row) for row in script.listing(ctx)]}


def _part(ctx: Ctx, x: dict, flags: dict) -> dict:
    clip = x["clip"] if made.there(ctx, x["clip"]) is not None else None
    return {"id": x["id"], "shot": x["shot"], "part": x["part"], "of": x["of"], "start_ms": round(x["start_ms"], 3),
            "end_ms": round(x["end_ms"], 3), "frames": x["n"], "render_frames": x["render"], "who": list(x["who"]),
            "lines": len(x["lines"]), "split": x["split"], "state": x["state"],
            "clip": {"id": clip, "url": ctx.files.url(clip)} if clip else None, "flag": flags.get(x["key"])}


def detail(ctx: Ctx, value: Any) -> dict:
    """The Detail; an unknown name raises (400)."""
    name = script.name_of(value)
    body = script.load(ctx, name)
    row = {"name": name, **(script.summary(body) if isinstance(body, dict) else {"seconds": None, "shots": None}),
           "why": None}
    found = None
    try:
        found = render.plan(ctx, name)
    except Invalid as e:
        row["why"] = e.text
    out = {**_script(ctx, row), "problem": memory(name)["problem"], "parts": None, "order": None}
    if found is not None:
        flags = memory(name)["flags"]
        out["parts"] = [_part(ctx, x, flags) for x in found["parts"]]
    job = live(ctx, name)
    fin = getattr(job.plan, "finish", None) if job is not None else None
    if isinstance(fin, render.Finish):
        out["order"] = [pid for _, pid, _, _ in fin.rendered]
    return out


async def get_scripts(ctx: Ctx, request: Request) -> dict:
    return await asyncio.to_thread(scripts, ctx)


async def get_script(ctx: Ctx, request: Request) -> dict:
    return await asyncio.to_thread(detail, ctx, request.query_params.get("name"))


async def _name(request: Request) -> str:
    try:
        body = json.loads(await request.body())
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise Invalid("body", "Send a JSON object")
    return script.name_of(body.get("name"))


def press(ctx: Ctx, name: str) -> dict:
    """Render: the job submitted, or the one line that refuses it."""
    mine = memory(name)
    if live(ctx, name) is not None:
        mine["problem"] = BUSY.format(name)
        return {"problem": mine["problem"]}
    render.pending.pop(name, None)
    try:
        made_job = ctx.jobs.submit(render.KIND, {"script": name})
    except Exception as exc:  # noqa: BLE001  (Invalid, or the queue's own refusal: its one line)
        slices.remove(render.pending.pop(name, []))    # cut for a job the queue did not take
        said = str(getattr(exc, "text", None) or exc).strip().splitlines()
        mine["problem"] = said[0] if said else type(exc).__name__
        return {"problem": mine["problem"]}
    render.pending.pop(name, None)
    fin = made_job.plan.finish
    if isinstance(fin, render.Finish):
        fin.job = made_job.id
    running[name] = made_job.id
    mine.update(state=made_job.state, problem=None)
    rendered = len(fin.rendered) if isinstance(fin, render.Finish) else 0
    return {"job": made_job.id, "render": rendered, "reused": fin.reused if isinstance(fin, render.Finish) else 0}


async def post_render(ctx: Ctx, request: Request) -> dict:
    name = await _name(request)
    try:
        return press(ctx, name)
    finally:
        publish(ctx, name)


async def on_finished(ctx: Ctx, data: dict) -> None:
    """`job.finished` of a Render: its state (and error line) kept, `running` dropped, the tab told."""
    if data.get("kind") != f"{ctx.module_id}.{render.KIND}":
        return
    job = ctx.jobs.get(data.get("job"))
    fin = getattr(getattr(job, "plan", None), "finish", None)
    name = fin.name if isinstance(fin, render.Finish) else next(
        (n for n, j in running.items() if j == data.get("job")), None)
    if name is None:
        return
    mine = memory(name)
    mine["state"] = str(data.get("state") or "done")
    mine["problem"] = getattr(job, "error", None) if mine["state"] == "failed" else None
    if running.get(name) == data.get("job"):
        running.pop(name, None)
    publish(ctx, name)


ROUTES = (Route("GET", "/scripts", get_scripts),
          Route("GET", "/script", get_script),
          Route("POST", "/render", post_render, body_limit=4096))
