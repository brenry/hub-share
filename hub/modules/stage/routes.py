"""The Stage routes, mounted at `/api/stage`. A refusal of a press is one line, HTTP 200 `{problem}`;
a request that is not one (a body that is no object, an unknown audience, no such set) is the Hub's 400
`{field, text}`. Every change is told to the tab as `stage.changed {name}` (an approve adds `revision`).

  File       = {id, url, thumb: url | null}               a media id with its versioned addresses
  Picture    = {id, keep}
  Summary    = {name, approved, revision: int | null, audience, house: bool, thumb: url | null, state}
  Draft      = {mode, state, job, problem, model, words, pan: File | null, plates: {plate: File} | null}
  Approved   = {record, plates: {wide, left, centre, right, audience: File}, house: {wide, left, right, row: File}
                | null, pan_url, house_pan_url: url | null, pictures: [File]}
  Detail     = {name, inputs: {pictures: [Picture], description, pieces: [str], audience, house: {era, dress, hair,
                size}}, approved: Approved | null, draft: Draft | null, prompts: {stage, house}}
`audience` none | heard | seen; `mode` build | change | house | house-change; `state` none | rendering | ready |
failed. `inputs` are the draft's, else the record's (the input pictures, `sets/<Set>/pictures/*` ids), else empty with
box 1's Keep empty; `Draft.plates` the new plates (Temp ids) when ready; `Approved` the record's files, versioned.
`prompts` the Prompt boxes (in memory only): a press's `prompt`, given, is set first as its pan's box (stage:
build, change; house: house, house change; any length), sent after the fields (`prompt.py`).

GET  /sets                                   -> {sets: [Summary], prompts}   approved sets and drafts, by name
GET  /set?name=                              -> Detail                 neither approved nor drafted: 400
POST /build {name, pictures, description, pieces, audience, prompt?}  -> {job} | {problem}
POST /again {name}                           -> {job} | {problem}      the draft's mode and inputs, again, no seed
POST /change {name, words, prompt?}          -> {job} | {problem}
POST /house {name, era, dress, hair, size, prompt?}  -> {job} | {problem}
POST /house-change {name, words, prompt?}    -> {job} | {problem}
POST /approve {name}                         -> {record} | {problem}
POST /discard {name}                         -> {ok: true}             the draft dropped (its running job cancelled)
POST /audience {name, audience}              -> {record} | {problem}   approved sets only
POST /delete {name}                          -> {ok: true} | {problem}
GET  /pan?name=&which=stage|house            -> the approved MP4 (no-store)
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from starlette.requests import Request
from starlette.responses import FileResponse

from hub.core.api import Ctx, Invalid, plain_name

from . import change, drafts, prompt, record

KIND, LENGTH = "pan", 175
NO_BOX_1 = "Put a picture of the set in box 1"
NO_PICTURE = "Box {} holds no picture"
RUNNING = "{} is being rendered now"
APPROVED = "{} is approved: ask for a change, or build a new set under another name"
FIRST = "Approve {}'s plates first"
HOUSE_FIRST = "Approve {}'s house first"
BUILD_FIRST = "Build {} first"
SAY = "Say the change"
NO_SET = "No set is called {}"
AUDIENCE = "Audience is none, heard or seen"
NOT_A_LIST = "{} must be a list"
job, NOT_RUNNING = drafts.job, drafts.NOT_RUNNING     # the `pan` job kind


async def _body(request: Request) -> dict[str, Any]:
    try:
        body = json.loads(await request.body())
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise Invalid("body", "Send a JSON object")
    return body


def _refused(ctx: Ctx, name: str, line: str) -> dict[str, Any]:
    draft = drafts.get(name)
    if draft is not None:
        draft["problem"] = line
        drafts.publish(ctx, draft["name"])
    return {"problem": line}


def _submit(ctx: Ctx, draft: dict[str, Any], params: dict[str, Any], **sets: Any) -> dict[str, Any]:
    """One job for `params`, no seed; -> {job} or {problem}. In the event loop: the core's book is
    not for another thread. `sets` are written on the draft only when the job is queued."""
    name = draft["name"]
    try:
        made = ctx.jobs.submit(KIND, {**params, "name": name, "mode": sets.get("mode", draft["mode"])})
    except Exception as exc:  # noqa: BLE001  (Invalid, or the core's Refused: its one line is the reason)
        return _refused(ctx, name, getattr(exc, "text", None) or str(exc) or "The pan could not be queued")
    summary = made.plan.summary
    draft.update(sets, params=params, seed=None, job=made.id, model=summary.get("model"), state="rendering",
                 facts={"frames": summary.get("frames"), "fps": summary.get("fps")}, pan=None, plates=None,
                 problem=None)
    drafts.put(draft)
    drafts.publish(ctx, name)
    return {"job": made.id}


def _params(pictures: list[Any], text: str, grabs: dict[str, int]) -> dict[str, Any]:
    return {"pictures": [str(p) for p in pictures], "prompt": text, "length": LENGTH, "grabs": list(grabs.values())}


async def _approved(ctx: Ctx, body: dict[str, Any]) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None]:
    """(the set's name, its record or None, its draft or None) for a press on a set; a name not plain: Invalid."""
    name = plain_name(body.get("name"), "name", "set")
    held = await asyncio.to_thread(record.read, ctx, name)
    draft = drafts.current(ctx, name)
    name = await asyncio.to_thread(record.find, ctx, name) or (draft["name"] if draft else name)   # its folder
    return name, held, draft


async def _press(ctx: Ctx, request: Request, act: Any) -> dict[str, Any]:
    """A press on a set: its refusals one line; busy refused before `act(ctx, body, name, record, draft)` runs."""
    body = await _body(request)
    try:
        name, held, draft = await _approved(ctx, body)
    except Invalid as exc:
        return {"problem": exc.text}
    if drafts.busy(ctx, draft):
        return _refused(ctx, name, RUNNING.format(name))
    try:
        return act(ctx, body, name, held, draft or drafts.fresh(name, drafts.record_inputs(name, held) if held
                                                            else drafts.empty_inputs()))
    except Invalid as exc:
        return _refused(ctx, name, exc.text)


def _build(ctx: Ctx, body: dict[str, Any], name: str, held: Any, draft: dict[str, Any]) -> dict[str, Any]:
    box = drafts.set_box("stage", body.get("prompt"))      # over the cap: the refusal
    if held is not None:
        return _refused(ctx, name, APPROVED.format(name))
    audience = body.get("audience", "seen")
    boxes = [b if isinstance(b, dict) else {} for b in body.get("pictures") or []]
    pieces = [p for p in (prompt.line(x) for x in body.get("pieces") or []) if p]
    draft["inputs"] = {**draft["inputs"], "description": prompt.line(body.get("description")), "pieces": pieces,
                       "audience": audience, "pictures": [{"id": str(b.get("id") or ""),
                                                           "keep": prompt.line(b.get("keep"))} for b in boxes]}
    drafts.put(draft)
    pictures = draft["inputs"]["pictures"]
    for n, pic in enumerate(pictures, 1):
        if ctx.files.kind(pic["id"]) != "image":
            raise Invalid("pictures", NO_BOX_1 if n == 1 else NO_PICTURE.format(n))
    if not pictures:
        raise Invalid("pictures", NO_BOX_1)
    text = prompt.build(pictures, draft["inputs"]["description"], pieces, box)
    return _submit(ctx, draft, _params([p["id"] for p in pictures], text, record.STAGE), mode="build", words=None,
                   op=None)


def _change(ctx: Ctx, body: dict[str, Any], name: str, held: Any, draft: dict[str, Any]) -> dict[str, Any]:
    box = drafts.set_box("stage", body.get("prompt"))      # over the cap: the refusal
    if held is None:
        return _refused(ctx, name, FIRST.format(name))
    words = prompt.line(body.get("words"))
    if not words:
        return _refused(ctx, name, SAY)
    op = change.parse(words, held)
    text = prompt.change(words, op, change.apply(held, op), box)
    plates = record.ids(name, held)["plates"]
    return _submit(ctx, draft, _params([plates[p] for p in record.STAGE], text, record.STAGE), mode="change",
                   words=words, op=op)


def _house(ctx: Ctx, body: dict[str, Any], name: str, held: Any, draft: dict[str, Any]) -> dict[str, Any]:
    box = drafts.set_box("house", body.get("prompt"))      # over the cap: the refusal
    if held is None:
        return _refused(ctx, name, FIRST.format(name))
    words = {k: prompt.line(body.get(k)) for k in drafts.HOUSE_WORDS}
    draft["inputs"] = {**draft["inputs"], "house": words}
    text = prompt.house(words, box)
    plates = record.ids(name, held)["plates"]
    return _submit(ctx, draft, _params([plates["audience"], plates["wide"]], text, record.HOUSE), mode="house",
                   words=None, op=None)


def _house_change(ctx: Ctx, body: dict[str, Any], name: str, held: Any, draft: dict[str, Any]) -> dict[str, Any]:
    box = drafts.set_box("house", body.get("prompt"))      # over the cap: the refusal
    if held is None:
        return _refused(ctx, name, FIRST.format(name))
    found = record.ids(name, held)
    if not found["house"]:
        return _refused(ctx, name, HOUSE_FIRST.format(name))
    words = prompt.line(body.get("words"))
    if not words:
        return _refused(ctx, name, SAY)
    text = prompt.house_change(words, held.get("house") or {}, box)
    pictures = [*(found["house"][p] for p in record.HOUSE), found["plates"]["audience"]]
    return _submit(ctx, draft, _params(pictures, text, record.HOUSE), mode="house-change", words=words, op=None)


def _again(ctx: Ctx, body: dict[str, Any], name: str, held: Any, draft: dict[str, Any]) -> dict[str, Any]:
    if not draft.get("params"):
        return _refused(ctx, name, BUILD_FIRST.format(name))
    return _submit(ctx, draft, draft["params"])


async def post_build(ctx: Ctx, request: Request) -> dict[str, Any]:
    body = await _body(request)                                     # not a press: a 400
    if body.get("audience", "seen") not in record.AUDIENCES:
        raise Invalid("audience", AUDIENCE)
    for key in ("pictures", "pieces"):
        if not isinstance(body.get(key, []), list):
            raise Invalid(key, NOT_A_LIST.format(key.capitalize()))
    return await _press(ctx, request, _build)


def _route(act: Any) -> Any:
    async def press(ctx: Ctx, request: Request) -> dict[str, Any]:
        return await _press(ctx, request, act)
    return press


post_again, post_change = _route(_again), _route(_change)
post_house, post_house_change = _route(_house), _route(_house_change)


async def post_approve(ctx: Ctx, request: Request) -> dict[str, Any]:
    name, _, draft = await _approved(ctx, await _body(request))
    if draft is None:
        return {"problem": record.NOT_READY}
    try:
        written = await asyncio.to_thread(record.approve, ctx, draft)
    except Invalid as exc:
        return _refused(ctx, name, exc.text)
    except (OSError, ValueError) as exc:               # the set's folder cannot take it: nothing of it was kept
        reason = getattr(exc, "strerror", None) or str(exc) or type(exc).__name__
        return _refused(ctx, name, record.UNWRITTEN.format(name, reason))
    if drafts.get(name) is draft:                      # not a draft an Again made while the copies ran
        drafts.drop(name)
    revision = written.get("revision")
    drafts.publish(ctx, name, revision=revision)
    if draft["mode"] != "build":
        ctx.emit("set.changed", {"name": name, "revision": revision})
    return {"record": written}


async def post_discard(ctx: Ctx, request: Request) -> dict[str, Any]:
    name, _, draft = await _approved(ctx, await _body(request))
    if draft is not None:
        if drafts.busy(ctx, draft):
            ctx.jobs.cancel(draft["job"])
        drafts.drop(name)
    drafts.publish(ctx, name)
    return {"ok": True}


async def post_audience(ctx: Ctx, request: Request) -> dict[str, Any]:
    body = await _body(request)
    if body.get("audience") not in record.AUDIENCES:
        raise Invalid("audience", AUDIENCE)
    name, held, draft = await _approved(ctx, body)
    if held is None:
        return _refused(ctx, name, FIRST.format(name))
    written = await asyncio.to_thread(record.set_audience, ctx, name, body["audience"])
    if draft is not None:
        draft["inputs"]["audience"] = body["audience"]
    drafts.publish(ctx, name)
    return {"record": written}


async def post_delete(ctx: Ctx, request: Request) -> dict[str, Any]:
    name, held, draft = await _approved(ctx, await _body(request))
    if held is None and draft is None:
        raise Invalid("name", NO_SET.format(name))
    if drafts.busy(ctx, draft):
        return _refused(ctx, name, RUNNING.format(name))
    try:
        await asyncio.to_thread(record.delete, ctx, name)
    except OSError as exc:
        return _refused(ctx, name, record.UNWRITTEN.format(name, exc.strerror or type(exc).__name__))
    drafts.drop(name)
    drafts.publish(ctx, name)
    return {"ok": True}


async def get_sets(ctx: Ctx, request: Request) -> dict[str, Any]:
    def build() -> dict[str, dict[str, Any] | None]:
        return {n: record.read(ctx, n) for n in record.names(ctx)}
    found = await asyncio.to_thread(build)
    every = {d["name"].casefold(): d["name"] for d in drafts.every()} | {n.casefold(): n for n in found}
    return {"sets": [drafts.summary(ctx, n, found.get(n), drafts.current(ctx, n))
                     for n in sorted(every.values(), key=str.casefold)], "prompts": drafts.boxes()}


async def get_set(ctx: Ctx, request: Request) -> dict[str, Any]:
    name, held, draft = await _approved(ctx, {"name": request.query_params.get("name")})
    if held is None and draft is None:
        raise Invalid("name", NO_SET.format(name))
    inputs = draft["inputs"] if draft else drafts.record_inputs(name, held) if held else drafts.empty_inputs()
    return {"name": name, "inputs": inputs, "approved": record.approved(ctx, name, held) if held else None,
            "draft": drafts.view(ctx, draft) if draft else None, "prompts": drafts.boxes()}


async def get_pan(ctx: Ctx, request: Request) -> FileResponse:
    name, held, _ = await _approved(ctx, {"name": request.query_params.get("name")})
    which = request.query_params.get("which") or "stage"
    path = record.root(ctx) / name / ("house/" if which == "house" else "") / record.PAN
    if held is None or which not in ("stage", "house") or not path.is_file():
        raise Invalid("name", f"{name} has no approved {'house ' if which == 'house' else ''}pan")
    return FileResponse(path, media_type="video/mp4", headers={"cache-control": "no-store"})
