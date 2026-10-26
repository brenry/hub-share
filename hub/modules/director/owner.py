"""Edits on the Storyboard's timeline: POST `/edit {name, op, ...}`, each op one
write of the script tools' own functions on the Storyboard's open script (`tools._write` with its name; not the chat's
open one, and not through `say.heard`: an edit, not a chat message), its answer the tool's (`{script, state,
gaps?, more?}`), a refusal `{problem}` in one plain line. A locked script is unlocked in the write and settled after it,
as every tool write is.

- `move {id, start_ms, shot?}`: a line, cue or pose by `event_move` (`start_ms` after the start of its shot, or of
  `shot`, which it moves into); a shot moves within its scene to the place of `shot`, else to where `start_ms` (script
  time) falls among its scene's other shots (their middles), and the script is timed again.
- `change {id, fields}`: `event_change` (a line's words, language, emotion, pace; a cue's; a pose's; a shot's camera);
  a line's `speaker` (one of its scene's cast) is changed here, the rest by `event_change`.
- `add_line {shot, speaker, words, start_ms?}`, `add_cue {shot, cue, words, start_ms?}`: `line_add`, `cue_add`, then
  `event_move` to `start_ms` when given. `add_shot {scene, camera, after?}`: `shot_add`. `remove {id}`: `event_remove`.
"""
from __future__ import annotations

import copy
from typing import Any

from hub.core.api import Ctx, Invalid, schema_check

from . import cards, edit, frame, importer, refs, render, routes, schemas, scripts, timing
from .layout import refuse

NO_SCRIPT = "There is no script named {}"
SHORT = "The scenes before the last already run {} s"    # nothing written
OPS = {
    "move": schemas._obj({"id": schemas.ID, "start_ms": schemas.MS, "shot": schemas.ID}, ("id", "start_ms")),
    "change": schemas._obj({"id": schemas.ID, "fields": {"type": "object", "maxProperties": 5}}, ("id", "fields")),
    "add_line": schemas._obj({"shot": schemas.ID, "speaker": schemas._s(), "words": schemas._s(),
                              "start_ms": schemas.MS}, ("shot", "speaker", "words")),
    "add_cue": schemas._obj({"shot": schemas.ID, "cue": schemas.INPUT["cue_add"]["properties"]["cue"],
                             "words": schemas._s(), "start_ms": schemas.MS}, ("shot", "cue", "words")),
    "add_shot": schemas.INPUT["shot_add"],
    "remove": schemas._obj({"id": schemas.ID}, ("id",)),
    "member": schemas._obj({"member": schemas._s(), "field": {"type": "string", "enum": list(cards.MEMBER_FIELDS)},
                            "value": {"type": "string"}}, ("member", "field", "value")),
    "import": schemas._obj({"text": {"type": "string"}}, ("text",)),
    "length": schemas._obj({"seconds": {"type": "integer", "minimum": 1}}, ("seconds",)),
    "set": schemas._obj({"field": {"type": "string", "enum": list(cards.SET_FIELDS)},
                         "value": {"type": "string"}}, ("field", "value")),
}


def _shot_of(script: dict, ident: str) -> tuple[int, dict, dict] | None:
    for n, scene in enumerate(script["scenes"], 1):
        for one in scene["shots"]:
            if one.get("id") == ident:
                return n, scene, one
    return None


def shot_move(script: dict, args: dict, pace: float | None = None) -> dict:
    """A shot to another place in its scene (the module docstring), the script timed again."""
    before = copy.deepcopy(script)
    n, scene, one = _shot_of(script, args["id"]) or (0, {}, {})
    others = [s for s in scene["shots"] if s is not one]
    if "shot" in args:                                   # its place: after it moving later, before it earlier
        m, target = edit.find_shot(script, args["shot"])
        if m != n:
            raise refuse(f"Shot {one['id']} is in scene {n}, shot {target.get('id')} in scene {m}",
                         "Move a shot within its scene")
        k = scene["shots"].index(target)
    else:
        k = sum(1 for s in others if (s["start_ms"] + s["end_ms"]) / 2 < args["start_ms"])
    scene["shots"].remove(one)
    scene["shots"].insert(k, one)
    moved = timing.retime(before, script, None, "move", pace)[1]
    return {"did": f"moved shot {one['id']} · scene {n} · {k + 1} of {len(scene['shots'])}", "shot": one,
            "scene": n, "moved": moved}


def speaker(script: dict, args: dict, value: Any, pace: float | None = None) -> dict:
    """A line's speaker, one of its scene's cast."""
    before = copy.deepcopy(script)
    n, one, ev = edit.find_event(script, args["id"])
    if ev["kind"] != "line" or not isinstance(value, str) or not value.strip():
        raise refuse("Only a line has a speaker", "Change a line's speaker to one of its scene's cast")
    ev["speaker"] = edit._member(script, n, value, "line")
    moved = timing.retime(before, script, ev, "change", pace)[1]
    return {**edit._done(ev, one, "changed "), "scene": n, "moved": moved}


def _then_move(done: dict, script: dict, start: int | None, pace: float | None) -> dict:
    if start is None:
        return done
    got = edit.event_move(script, {"id": done["acted"], "start_ms": start}, pace=pace)
    return {**got, "did": f"{done['did']} · {got['did']}"}


def change(op: str, args: dict, pace: float) -> Any:
    """The write's change `fn(script, counters, characters)` of one op."""
    def fn(script: dict, counters: dict, characters: Any) -> dict:
        shot_id = args.get("id") if op in ("change", "remove", "move") else None
        held = next((sc for sc in script["scenes"] for sh in sc["shots"] if sh.get("id") == shot_id), None)
        if held is not None:                          # the edit sets the length: the scene's named one gives way
            held.pop("seconds", None)
        if op == "remove" and held is not None:          # a removed shot goes with everything in it
            shot = next(sh for sh in held["shots"] if sh.get("id") == shot_id)
            shot["events"] = [ev for ev in shot["events"] if ev.get("kind") == "panel"]
        if op == "move":
            if _shot_of(script, args["id"]) is not None:
                return shot_move(script, args, pace)
            return refs.TOOLS["event_move"](script, args, pace=pace)
        if op == "change":
            fields = dict(args["fields"])
            cam = fields.get("camera")
            if isinstance(cam, dict) and isinstance(cam.get("move"), str) and not cam["move"].strip():
                fields["camera"] = {k: v for k, v in cam.items() if k != "move"}   # an emptied move: taken off
                if held is not None:
                    for sh in held["shots"]:
                        if sh.get("id") == shot_id and isinstance(sh.get("camera"), dict):
                            sh["camera"].pop("move", None)
            who = fields.pop("speaker", None)
            done = speaker(script, args, who, pace) if "speaker" in args["fields"] else None
            if fields or done is None:
                done = refs.TOOLS["event_change"](script, {"id": args["id"], "fields": fields}, pace=pace)
            return done
        if op in ("add_line", "add_cue"):
            add = edit.line_add if op == "add_line" else edit.cue_add
            done = add(script, counters, {k: v for k, v in args.items() if k != "start_ms"}, pace=pace)
            return _then_move(done, script, args.get("start_ms"), pace)
        if op == "import":                               # a pasted H3 prompt: one shot per time range, at the end
            made = importer.shots(args["text"])
            if not script["scenes"]:
                raise Invalid("text", "The script has no scene to add the shots to")
            n = len(script["scenes"])
            script["scenes"][-1].pop("seconds", None)
            for seconds, prompt in made:
                frame.shot_add(script, counters, {"scene": n, "camera": {}, "seconds": seconds, "action": prompt})
            return {"did": f"imported {len(made)} shot{'' if len(made) == 1 else 's'}"}
        if op == "length":                               # the video's length as typed: the last scene's named one
            scenes = script["scenes"]
            if not scenes:
                raise Invalid("seconds", "There is no scene to give a length")
            last = scenes[-1]
            before = (last["shots"][0]["start_ms"] if last["shots"] else 0) // 1000
            rest = int(args["seconds"]) - before
            if rest < 1:
                raise Invalid("seconds", SHORT.format(before))
            last["seconds"] = rest
            return {"did": f"the video's length set to {args['seconds']} s"}
        if op == "member":
            return cards.member(script, args["member"], args["field"], args["value"])
        if op == "set":
            return cards.set_field(script, args["field"], args["value"])
        if op == "add_shot":
            return frame.shot_add(script, counters, args)
        return refs.TOOLS["event_remove"](script, args, pace=pace)
    return fn


async def edit_op(ctx: Ctx, body: dict) -> dict:
    """One op on the named script: the tool's answer, or `{problem}`."""
    from . import tools  # late: tools reads this module's neighbours

    try:
        name = scripts.name_of(body.get("name"))
        if not scripts.exists(routes.folder(ctx), name):
            raise Invalid("name", NO_SCRIPT.format(name))
        op = body.get("op")
        if op not in OPS:
            raise Invalid("op", f"op is one of {', '.join(OPS)}")
        args = schema_check(OPS[op], {k: v for k, v in body.items() if k not in ("name", "op")})
        return await tools._write(ctx, change(op, args, tools._pace(ctx)), None, name)
    except Invalid as e:
        return {"problem": render.plain(e)}
