"""The Casting routes, mounted at `/api/casting`. A refusal of Cast, Again or Approve is one line,
answered as `{problem}` (HTTP 200); a request that is not one (no such character, a body that is no object) is the
Hub's usual 400 `{field, text}`. Every change to a draft is told to the tab as `casting.changed` on lane
`casting.changed`, `{name}` (a costume's `{name, variant}`).

GET  /list              -> [{name, picture, cast, role, costumes}]   every character in Characters by name: `picture`
                           its picture's media id (`chars/Character 1.png`); `cast` when its folder holds an approved
                           record; `role` that record's "cast" | "audience", or null; `costumes` how many it holds.
GET  /draft?name=       -> {name, picture, state, headshot: {id, keep, ignore}, bits: [{id, keep, ignore}],
                           facts: {age, build}, model, job, orbit, views, problem, record, files, role, seat,
                           costumes, prompt}
                           `state` none | rendering | ready | failed | approved; `job` the last cast's job id (its
                           card on the jobs lane) or null; `orbit` the orbit clip's media id or null; `views`
                           {front, left, back, right, face-1, face-2: media id} or null; `problem` one line or null;
                           `model` the model's name the last cast ran on, or null. `record` its approved
                           `casting.json` or null; `files` null, or its files {views: {view: media id}, bits: [media
                           id], view_urls: {view: url}, view_thumbs: {view: url}, bit_urls: [url], orbit_url}: the ids
                           bare (as Media takes them), each url with its version `?v=<mtime>` (as `/files/…` and
                           `/thumbs/…` urls are given everywhere), `orbit_url` `/api/casting/orbit?name=…&v=<mtime>`
                           (the approved orbit is no media item). A re-approve gives new urls: no stale cache.
                           Before any cast its lines are the headshot's defaults, or the approved record's.
                           `role` "cast" | "audience" (the record's, else "cast"); `seat` {side: left | centre |
                           right, row: 1-12} (the record's, else centre, 1); `views` and `files.views` hold the role's
                           views only (audience: front, left, right, face-1); `costumes` [{variant, state, approved:
                           bool, earlier: bool (cast from a face before its record's approved one), thumb: url|null}]:
                           its record's costumes, then those only in memory. `prompt` the tab's Prompt box,
                           one text for every cast and costume, in memory only, "" after a restart.
POST /cast {name, headshot: {keep, ignore}, bits: [{id, keep, ignore}], facts: {age, build}, role?, seat?, prompt?}
                        -> {job} | {problem}     one job `casting.orbit`: the orbit, then its six views (audience:
                           107 frames, four views, its card `Cast · <Name> · audience · <n> pictures`). `prompt`,
                           given, is the box, set first (as typed, any length); the
                           cast's prompt is its fields, then the box when it holds text (`prompt.prompt`).
POST /again {name}      -> {job} | {problem}     the draft's pictures, lines and facts, rendered again (no seed).
POST /approve {name}    -> the record written (as `casting.json`) | {problem}
POST /seat {name, seat: {side, row}}
                        -> {seat, record: obj|null} | {problem}   the draft's seat; its record's `seat` alone
                           rewritten when its record is audience (`record` then the record written, else null).
GET  /orbit?name=&variant=  -> its approved `orbit.mp4`; with `variant`, that costume's
GET  /costume?name=&variant=
                        -> {name, variant, state, faces: [id, id], face_thumbs: [url, url], pictures: [{id, keep,
                           ignore}], words, job, orbit, views, model, problem, from, prompt (the box), record: the
                           costume's entry|null,
                           files: null | {views, view_urls, view_thumbs, pictures: [id], picture_urls: [url],
                           orbit_url}}   a name not yet a costume: a fresh draft, state "none"; `variant` the
                           costume's name as its record or draft has it.
POST /costume/cast {name, variant, pictures: [{id, keep, ignore}], words, prompt?}   -> {job} | {problem}   card
                           `Cast · <Name> · <costume> · <n> pictures` (n counts its two face frames)
POST /costume/again {name, variant}     -> {job} | {problem}
POST /costume/approve {name, variant}   -> the costume's entry written | {problem}
POST /costume/remove {name, variant}    -> {removed: variant} | {problem}
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import PurePosixPath
from typing import Any

from starlette.requests import Request
from starlette.responses import FileResponse

from hub.core.api import Ctx, Invalid, JobPlan, write_json

from . import prompt, record, state, variants

MAX_PICTURES = 9
KIND = "orbit"
NOT_RUNNING = "Generate Image is not running"
TOO_MANY = "Casting takes at most {} pictures; this has {}"
NOT_A_PICTURE = "Box {} holds no picture"
RUNNING = "{} is being cast now"
NOTHING = "Cast {} first"
NO_ORBIT = "{} has no approved orbit"
ROLES = ("cast", "audience")


async def _body(request: Request) -> dict[str, Any]:
    try:
        body = json.loads(await request.body())
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise Invalid("body", "Send a JSON object")
    return body


def _who(ctx: Ctx, name: Any) -> tuple[str, str]:
    """(the character's name as Characters has it, its picture's id); else one line."""
    found = ctx.files.character(name) if isinstance(name, str) and name.strip() else None
    if found is None:
        raise Invalid("name", f"No character is called {name if isinstance(name, str) else ''}".strip())
    return PurePosixPath(found).stem, found


def _busy(ctx: Ctx, draft: dict[str, Any]) -> str | None:
    """The line when the draft's last cast is still queued or running, else None."""
    held = ctx.jobs.get(draft["job"]) if draft.get("job") else None
    return RUNNING.format(draft["name"]) if held is not None and held.state in ("queued", "running") else None


def _lines(value: Any) -> dict[str, str]:
    value = value if isinstance(value, dict) else {}
    return {"keep": prompt.line(value.get("keep")), "ignore": prompt.line(value.get("ignore"))}


def job(params: dict, ctx: Ctx) -> JobPlan:
    """The `orbit` job kind: Generate's orbit (`ctx.service("orbit")`), its card titled `Cast · <Name> · <n>
    pictures` (`Cast · <Name> · <costume|audience> · <n> pictures`). Frames and views go to the service only when the
    params carry them (else the service's own: the cast's 124 frames and six views)."""
    try:
        plan_of = ctx.service("orbit")
    except Invalid:
        raise Invalid("model", NOT_RUNNING) from None
    pictures = list(params.get("pictures") or [])
    shape = (params["frames"], params.get("views")) if "frames" in params else ()
    plan = plan_of(pictures, params.get("prompt"), params.get("seed"), *shape)
    n = len(pictures)
    what = params.get("variant") or ("audience" if params.get("role") == "audience" else None)
    title = " · ".join(t for t in ("Cast", str(params.get("name")), what,
                                   f"{n} {'picture' if n == 1 else 'pictures'}") if t)
    return dataclasses.replace(plan, summary={**plan.summary, "title": title})


def queue(ctx: Ctx, draft: dict[str, Any], build: Any) -> dict[str, Any]:
    """One job of `build()`'s params, no seed (the engine's own); -> {job} or {problem} (kept on the
    draft too). In the event loop: the core's book is not for another thread."""
    name, variant = draft["name"], draft.get("variant")
    try:
        params = build()
        made = ctx.jobs.submit(KIND, params)
    except Exception as exc:  # noqa: BLE001  (Invalid, or the core's Refused: its one line is the reason)
        line = getattr(exc, "text", None) or str(exc) or "The cast could not be queued"
        draft["problem"] = line
        state.publish(ctx, name, variant)
        return {"problem": line}
    cast_as = "audience" if params.get("role") == "audience" else "cast"      # what this job makes, kept apart
    draft.update(state="rendering", seed=None, job=made.id, model=made.plan.summary.get("model"), orbit=None,
                 views=None, problem=None, cast_as=cast_as, expect=list(record.SHEETS[cast_as]))
    state.publish(ctx, name, variant)
    return {"job": made.id}


def set_box(body: dict[str, Any]) -> str | None:
    """The body's `prompt`, when given, set as the tab's box first; -> the refusal's one line, else None."""
    try:
        state.set_box(body.get("prompt"))
    except Invalid as exc:
        return exc.text
    return None


def _cast(ctx: Ctx, draft: dict[str, Any], role: str | None = None, seat: Any = None) -> dict[str, Any]:
    """A cast (or an extra's): the picture and bits, their lines and facts, then the box. `role` and `seat` (else
    the draft's) become the draft's only when the job is queued, so a refused cast leaves the role its views were made
    as."""
    role, seat = role or draft["role"], seat or draft["seat"]

    def build() -> dict[str, Any]:
        pictures = [draft["headshot"], *draft["bits"]]
        if len(pictures) > MAX_PICTURES:
            raise Invalid("bits", TOO_MANY.format(MAX_PICTURES, len(pictures)))
        for n, bit in enumerate(draft["bits"], 2):
            if ctx.files.kind(bit["id"]) != "image":
                raise Invalid("bits", NOT_A_PICTURE.format(n))
        params = {"name": draft["name"], "pictures": [p["id"] for p in pictures]}
        if role != "audience":
            return {**params, "prompt": prompt.prompt(pictures, draft["facts"], state.box())}
        if variants.entries(record.read(ctx, draft["name"])):
            raise Invalid("role", record.HAS_COSTUMES.format(draft["name"]))
        return {**params, "prompt": prompt.prompt(pictures, draft["facts"], state.box()), "role": "audience",
                "frames": record.EXTRA_FRAMES, "views": list(record.AUDIENCE.values())}
    answer = queue(ctx, draft, build)
    if "job" in answer:
        draft.update(role=role, seat=seat)
    return answer


async def get_list(ctx: Ctx, request: Request) -> list[dict[str, Any]]:
    def build() -> list[dict[str, Any]]:
        def one(c: dict[str, Any]) -> dict[str, Any]:
            found = record.read(ctx, c["name"])
            return {"name": c["name"], "picture": c["id"], "cast": record.cast(ctx, c["name"]),
                    "role": record.role_of(found) if found else None, "costumes": len(variants.entries(found))}
        return [one(c) for c in ctx.files.characters()]
    return await asyncio.to_thread(build)


async def get_draft(ctx: Ctx, request: Request) -> dict[str, Any]:
    name, picture = await asyncio.to_thread(_who, ctx, request.query_params.get("name"))
    return await asyncio.to_thread(state.view, ctx, name, picture)


async def post_cast(ctx: Ctx, request: Request) -> dict[str, Any]:
    body = await _body(request)
    name, picture = await asyncio.to_thread(_who, ctx, body.get("name"))
    if line := set_box(body):
        return {"problem": line}
    bits = body.get("bits") if isinstance(body.get("bits"), list) else []
    facts = body.get("facts") if isinstance(body.get("facts"), dict) else {}
    draft = state.current(ctx, name, picture)
    if line := _busy(ctx, draft):
        return {"problem": line}
    role = body.get("role", draft["role"])
    if role not in ROLES:
        raise Invalid("role", "A role is cast or audience")
    try:
        seat = record.seat_of(body["seat"]) if body.get("seat") is not None else draft["seat"]
    except Invalid as exc:
        return {"problem": exc.text}
    draft.update(headshot={"id": picture, **_lines(body.get("headshot"))},
                 bits=[{"id": str(b.get("id") or ""), **_lines(b)} for b in bits if isinstance(b, dict)],
                 facts={"age": prompt.line(facts.get("age")), "build": prompt.line(facts.get("build"))})
    state.put(draft)
    return _cast(ctx, draft, role, seat)


async def post_again(ctx: Ctx, request: Request) -> dict[str, Any]:
    body = await _body(request)
    name, picture = await asyncio.to_thread(_who, ctx, body.get("name"))
    draft = state.current(ctx, name, picture)
    if draft["state"] == "none":
        return {"problem": NOTHING.format(name)}
    if line := _busy(ctx, draft):
        return {"problem": line}
    state.put(draft)
    return _cast(ctx, draft)


async def post_approve(ctx: Ctx, request: Request) -> dict[str, Any]:
    body = await _body(request)
    name, picture = await asyncio.to_thread(_who, ctx, body.get("name"))
    draft = state.current(ctx, name, picture)
    try:
        written = await asyncio.to_thread(record.approve, ctx, draft)
    except Invalid as exc:
        return {"problem": exc.text}
    except (OSError, ValueError) as exc:               # the character's folder cannot take it: nothing of it was kept
        reason = getattr(exc, "strerror", None) or str(exc) or type(exc).__name__
        return {"problem": record.UNWRITTEN.format(name, reason)}
    draft.update(state="approved", problem=None)
    state.publish(ctx, name)
    return written


async def post_seat(ctx: Ctx, request: Request) -> dict[str, Any]:
    body = await _body(request)
    name, picture = await asyncio.to_thread(_who, ctx, body.get("name"))
    try:
        seat = record.seat_of(body.get("seat"))
    except Invalid as exc:
        return {"problem": exc.text}
    draft = state.put(state.current(ctx, name, picture))
    draft["seat"] = seat

    def save() -> dict[str, Any] | None:
        with record.LOCK:
            found = record.read(ctx, name)
            if found is None or record.role_of(found) != "audience":
                return None
            found["seat"] = seat
            write_json(record.home(ctx, name) / record.RECORD, found, 0o644)
            return found
    try:
        written = await asyncio.to_thread(save)
    except OSError as exc:
        return {"problem": record.UNWRITTEN.format(name, exc.strerror or str(exc))}
    state.publish(ctx, name)
    return {"seat": seat, "record": written}


async def get_orbit(ctx: Ctx, request: Request) -> FileResponse:
    name, _ = await asyncio.to_thread(_who, ctx, request.query_params.get("name"))
    variant = request.query_params.get("variant")
    path = (variants.orbit_path(ctx, name, variant) if variant else record.home(ctx, name) / record.ORBIT)
    if path is None or not path.is_file():
        raise Invalid("name", NO_ORBIT.format(f"{name} · {variant}" if variant else name))
    return FileResponse(path, media_type="video/mp4", headers={"cache-control": "no-store"})
