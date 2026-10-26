"""The Storyboard tab's HTTP routes, mounted at `/api/director` (a paired screen only).

GET `/scripts` (the listing), GET `/script?name=` (one script, or its problem; with `audio`, the audio
script's rows of a locked version-2 script, or of a complete one, else null), POST `/rename` `{name,
to}`, POST `/delete` `{name}` (the file, for good). Renaming the script the tools write moves their pointer and its id
counters; deleting it clears both. `/script` also gives each cast member's voice sample facts (`voices`), a
take's state as `Track` holds it, its file's address, measured and judged fields; POST `/track` `{name}` presses
Track.
`/script` also answers the mix's `track` {state, file?, url?, length_ms?, note?, why?} (stats only).

The answers:
- GET `/script` -> `{name, seconds, problem, script, pictures, unpictured, audio, track, rendering}`. `rendering`
  is the id of the Track job `track.running` holds for a locked version-2 script (after `track.prune`), else
  null; the queue's card of that id (`jobs` lane: `progress` {index, count, pct, ...} while running, `position`
  while queued, `summary.step_names`) is Track's progress. Each `audio` row's `take`: `{state, file?, why?,
  url?, measured?, judge?}`; `measured.gain_db` (the gain to -23 LUFS, or null) is the gain the take plays at; a
  `failed` take has `why` and a `file` only when an earlier take of it is still in Sounds.
- POST `/rename` `{name, to}` -> `{name}` (the new name); POST `/delete` `{name}` -> null. While the script's Track
  job is queued or running, both refused `{field: "name", text}` with the one line `<name>'s takes are rendering
  (job <id>): rename it when the job ends` (`delete it when the job ends`); nothing changed.
- POST `/track` `{name}` -> `{job, lines, takes, cues, room, note, notes}`, or, nothing to
  render, the mix's `{job, lines: 0, mixing: true, answer, note}`, or refused in one line; a second press
  while `rendering` is refused `busy`.
- `/script` also answers `rendering_cut` (the Render job's id while queued or running, else null), `cut`
  (the last Render's MP4 media id when its file is there, else null) and `cut_url` (its address, else null); POST
  `/render {name}` -> `{job, shots, skipped}` (`skipped`: one line per shot left out) or `{problem}`; POST `/edit
  {name, op, ...}` -> the tool's `{script, state, gaps?, more?}` or `{problem}` (`owner.py`). Neither waits on a lock.
- A Track job's every end (finished, failed, cancelled or refused while queued) publishes `director.changed`
  `{name, revision}` with `track.running` cleared, so `rendering` is null on the next read.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, NamedTuple

from starlette.requests import Request

from hub.core.api import Ctx, Invalid, Route, sound_exact

from . import audioscript, scripts


def folder(ctx: Ctx) -> Path:
    return ctx.files.roots[scripts.ROOT]


def characters(ctx: Ctx) -> dict[str, str]:
    """{folded name -> picture id} of Characters; empty when the folder is not chosen."""
    return {c["name"].casefold(): c["id"] for c in ctx.files.characters()}


class Voice(NamedTuple):
    """A cast member's voice sample: its path, size, modified time in whole seconds, and its length
    (`api.sound_exact`; None when it does not read as a WAV, or when not measured)."""
    path: Path
    size: int
    mtime_s: int
    seconds: float | None


def voices(ctx: Ctx, script: dict, measure: bool = False) -> dict[str, Voice]:
    """{folded name -> Voice} of each cast member with `<Name>.wav` beside its picture; `measure`: its length read
    (the lock and Track; `/script` only stats it)."""
    out = {}
    for member in script.get("context", {}).get("cast", []):
        path = ctx.files.character_sample(member["name"])
        if path is None:
            continue
        try:
            st = path.stat()
        except OSError:
            continue
        seconds = None
        if measure:
            try:
                seconds = float(sound_exact(path))
            except (OSError, ValueError):
                seconds = None
        out[member["name"].casefold()] = Voice(path, int(st.st_size), int(st.st_mtime), seconds)
    return out


def present(ctx: Ctx, takes: dict) -> set[str]:
    """The take files of `takes` that are files in Sounds: an existence check, never a read of the WAV
    (`files.sound_facts` would read it whole on every reload)."""
    root = ctx.files.roots["sounds"].resolve()
    out = set()
    for entry in takes.values():
        path = (root / entry["file"]).resolve()
        if path.is_relative_to(root) and path.suffix == ".wav" and path.is_file():
            out.add(entry["file"])
    return out


async def _body(request: Request) -> dict[str, Any]:
    try:
        body = json.loads(await request.body())
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise Invalid("body", "Send a JSON object")
    return body


async def get_scripts(ctx: Ctx, request: Request) -> dict:
    return {"scripts": await asyncio.to_thread(lambda: scripts.listing(folder(ctx), characters(ctx)))}


def _one(ctx: Ctx, name: Any) -> dict:
    """The script and, when it reads, is version 2 and locked or written, its audio script; nothing written."""
    from . import autolock, track  # late: they read this module

    found = scripts.one(folder(ctx), name, characters(ctx))
    script = found["script"]
    audio, rendering = None, None
    if script is not None and script["version"] == 2 and (script.get("lock", {}).get("locked") is True
                                                          or autolock.written(script)):

        track.prune(ctx, found["name"])
        rendering = (track.running.get(found["name"]) or {}).get("job")
        held = voices(ctx, script)
        takes = script.get("takes") or {}
        there = present(ctx, takes)
        audio = audioscript.plan(found["name"], script, {n: v.path.name for n, v in held.items()},
                                 {n: [v.size, v.mtime_s] for n, v in held.items()}, there, track.state(found["name"]))
        for row in audio:
            entry, got = takes.get(row["id"]), row["take"]
            if entry is not None and got["state"] in ("ok", "flagged", "stale") and got["file"] in there:
                got.update(url=ctx.files.url(f"sounds/{got['file']}"), measured=entry.get("measured"),
                           judge=entry.get("judge"))
    from . import render  # late: it reads this module

    cut = render.cut(ctx, found["name"])                                         # the last Render's cut
    return {**found, "audio": audio, "track": track_state(ctx, found["name"], script), "rendering": rendering,
            "rendering_cut": render.live(ctx, found["name"]), "cut": cut,
            "cut_url": ctx.files.url(cut) if cut else None}


def current(ctx: Ctx, name: str, script: dict) -> bool:
    """Whether the mix is current: the track a file in Sounds of its recorded size, the mix's hash a fresh
    placement's, and every shot and event measured."""
    from . import layout, mix  # late: mix reads this module

    renders = script.get("renders") or {}
    try:
        path = ctx.files.roots["sounds"] / str(renders.get("track") or "")
        if not renders.get("track") or not path.is_file() or path.stat().st_size != renders.get("size"):
            return False
        fresh = mix.build(ctx, name, script, read_room=False)["mix"]["hash"]
    except (Invalid, OSError):
        return False
    return fresh == (script.get("mix") or {}).get("hash") and all(
        "measured" in shot and all("measured" in ev for ev in shot["events"]) for shot in layout.shots(script))


def track_state(ctx: Ctx, name: str, script: dict | None) -> dict | None:
    """The mix's state (stats only, never a read of a WAV); None unless a locked version-2 script."""
    from . import mix  # late: mix reads this module

    if script is None or script["version"] != 2 or not script.get("lock", {}).get("locked"):
        return None
    mix.prune(ctx, name)
    held, track = script.get("mix") or {}, (script.get("renders") or {}).get("track")
    out: dict[str, Any] = {"note": held["note"]} if held.get("note") else {}
    there = bool(track) and (ctx.files.roots["sounds"] / track).is_file()
    if there:
        out.update(file=track, url=ctx.files.url(f"sounds/{track}"), length_ms=held.get("length_ms"))
    if name in mix.running:
        return {"state": "mixing", **out}
    if name in mix.failed:
        return {"state": "failed", "why": mix.failed[name], **out}
    return {"state": "none" if not there else "current" if current(ctx, name, script) else "stale", **out}


async def get_script(ctx: Ctx, request: Request) -> dict:
    name = request.query_params.get("name")
    return await asyncio.to_thread(_one, ctx, name)


def _follow(ctx: Ctx, name: str, to: str | None) -> None:
    """The tools' pointer and id counters after `name` was renamed to `to`, or deleted (None)."""
    pointer = ctx.doc("current", {"name": None})
    if pointer.get().get("name") == name:
        pointer.patch({"name": to})
    ids = ctx.doc("ids", {})
    counters = ids.get().get(name)
    if counters is not None or (to is not None and to in ids.get()):
        rest = {k: v for k, v in ids.get().items() if k not in (name, to)}
        ids.replace({**rest, **({to: counters} if to is not None and counters is not None else {})})


def _idle(ctx: Ctx, name: str, verb: str) -> None:
    """Refused while the script's Track job is queued or running, naming the job."""
    from . import track  # late: it reads this module

    track.prune(ctx, name)
    held = track.running.get(name)
    if held is not None:
        raise Invalid("name", f"{name}'s takes are rendering (job {held['job']}): {verb} it when the job ends")


async def post_rename(ctx: Ctx, request: Request) -> dict:
    body = await _body(request)
    name = scripts.name_of(body.get("name"))
    _idle(ctx, name, "rename")
    done = await asyncio.to_thread(scripts.rename, folder(ctx), name, body.get("to"))
    if done["name"] != name:
        _follow(ctx, name, done["name"])
    return done


async def post_delete(ctx: Ctx, request: Request) -> None:
    name = scripts.name_of((await _body(request)).get("name"))
    _idle(ctx, name, "delete")
    await asyncio.to_thread(scripts.delete, folder(ctx), name)
    _follow(ctx, name, None)


async def post_track(ctx: Ctx, request: Request) -> dict:
    """Track on the script of that name (the Storyboard's button): `{job, lines}`, or the job's one line. The press
    locks it, whatever its scenes say."""
    from . import track  # late: it reads this module

    name = scripts.name_of((await _body(request)).get("name"))
    return await track.press(ctx, name)


async def get_video_loras(ctx: Ctx, request: Request) -> dict:
    """The Storyboard's Video LoRAs: the files in `video_lora_folders`, each with its toggle and strength."""
    from . import videoloras
    return await asyncio.to_thread(videoloras.listing, ctx)


async def post_video_loras(ctx: Ctx, request: Request) -> dict:
    """One Video LoRA's toggle and/or strength -> the listing, or {problem}."""
    from . import videoloras
    try:
        return await asyncio.to_thread(videoloras.change, ctx, await _body(request))
    except Invalid as e:
        return {"problem": e.text}


async def get_shot_pictures(ctx: Ctx, request: Request) -> dict:
    """{pictures: {shot id: [item ids]}} of the script `name`: each shot's own pictures."""
    from . import shotpics
    return {"pictures": await asyncio.to_thread(shotpics.all_of, ctx, request.query_params.get("name") or "")}


async def post_shot_pictures(ctx: Ctx, request: Request) -> dict:
    """{name, shot, ids}: that shot's own pictures, in order ([] clears) -> {pictures} or {problem}."""
    from . import shotpics
    body = await _body(request)
    try:
        return await asyncio.to_thread(shotpics.put, ctx, str(body.get("name") or ""), str(body.get("shot") or ""),
                                       body.get("ids"))
    except Invalid as e:
        return {"problem": e.text}


async def post_render(ctx: Ctx, request: Request) -> dict:
    """Render the script of that name -> `{job, shots, skipped}` or `{problem}`."""
    from . import render  # late: it reads this module

    body = await _body(request)
    return render.press(ctx, body.get("name"), body.get("shot"))


async def post_edit(ctx: Ctx, request: Request) -> dict:
    """One edit op on the timeline (`owner.py`) -> the tool's answer or `{problem}`."""
    from . import owner  # late: it reads this module

    return await owner.edit_op(ctx, await _body(request))


async def start(ctx: Ctx) -> None:
    """The sketch panels' loop."""
    from . import drawing  # late: it reads this module

    await drawing.start(ctx)


ROUTES = (Route("GET", "/scripts", get_scripts),
          Route("GET", "/script", get_script),
          Route("POST", "/rename", post_rename),
          Route("POST", "/delete", post_delete),
          Route("POST", "/track", post_track),
          Route("POST", "/render", post_render, body_limit=4096),
          Route("GET", "/video-loras", get_video_loras),
          Route("GET", "/shot-pictures", get_shot_pictures),
          Route("POST", "/shot-pictures", post_shot_pictures, body_limit=8192),
          Route("POST", "/video-loras", post_video_loras, body_limit=4096),
          Route("POST", "/edit", post_edit, body_limit=16_384))
