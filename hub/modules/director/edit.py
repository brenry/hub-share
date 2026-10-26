"""The script tools' changes and their checks on arrival (blueprint A.3; R48 §2), pure: each
function changes a version-2 script in memory, in place (the caller holds a copy, `scripts.change`), and answers what
was done; a refusal is an `Invalid` whose text is the compact JSON `{problem, fix, hints}`, and the caller writes
nothing. One event per call. Ids are `s`, `l`, `c`, `p` and a number, never reused in a script: `counters` holds the
highest number given per prefix, beside what the file holds. Nothing is refused for its words. After each
change the script is timed again and checked (`timing.retime`), with the Hub's pace the caller hands in.
"""
from __future__ import annotations

import copy
import re
from typing import Any

from . import clock, hold, keys, layout, scriptshape, timing
from .layout import refuse  # the refusal's shape, also read as `edit.refuse`

PREFIX = {"line": "l", "cue": "c", "pose": "p"}
FIELDS = {"line": ("words", "language", "emotion", "pace"), "cue": ("cue", "words", "seconds"), "pose": ("pose",)}


def _numbers(script: dict, prefix: str) -> list[int]:
    found = [shot.get("id", "") for shot in layout.shots(script)] if prefix == "s" else \
        [ev["id"] for shot in layout.shots(script) for ev in shot["events"]]
    return [int(m.group(1)) for m in (re.fullmatch(rf"{prefix}([0-9]+)", i) for i in found) if m]


def next_id(script: dict, counters: dict, prefix: str) -> str:
    n = max([counters.get(prefix, 0), *_numbers(script, prefix)]) + 1
    counters[prefix] = n
    return f"{prefix}{n}"


def ensure_shot_ids(script: dict, counters: dict) -> None:
    """A shot without an id gets the next `s<n>`, in script order (a file written without shot ids, on its first
    write)."""
    for shot in layout.shots(script):
        if "id" not in shot:
            shot["id"] = next_id(script, counters, "s")


# ---------------------------------------------------------------- finding
def _scene(script: dict, n: int) -> dict:
    if not 1 <= n <= len(script["scenes"]):
        raise refuse(f"There is no scene {n}", "Name a scene by its number, or call scene_add",
                     scenes=[{"scene": k, "title": sc["title"]} for k, sc in enumerate(script["scenes"], 1)])
    return script["scenes"][n - 1]


def find_shot(script: dict, ident: str) -> tuple[int, dict]:
    """(its scene's number, the shot)."""
    for n, sc in enumerate(script["scenes"], 1):
        for shot in sc["shots"]:
            if shot.get("id") == ident:
                return n, shot
    raise refuse(f"There is no shot {ident}", "Name a shot of the script, or call shot_add",
                 shots=[shot.get("id") for shot in layout.shots(script)])


def find_event(script: dict, ident: str) -> tuple[int, dict, dict]:
    """(its scene's number, its shot, the event)."""
    ids = []
    for n, sc in enumerate(script["scenes"], 1):
        for shot in sc["shots"]:
            for ev in shot["events"]:
                if ev["id"] == ident:
                    return n, shot, ev
                ids.append(ev["id"])
    raise refuse(f"There is no event {ident}", "Name an event of the script (script_read lists them)", ids=ids)


def _member(script: dict, n: int, name: str, what: str) -> str:
    cast = script["scenes"][n - 1]["cast"]
    found = next((c for c in cast if c.casefold() == name.casefold()), None)
    if found is None:
        raise refuse(f"{name} is not in scene {n}'s cast", f"Give the {what} to one of the scene's cast, or add a "
                     "scene with this cast", valid_speakers=cast)
    return found


def _anchor(shot: dict, anchor: dict | None, sid: str) -> int | None:
    if anchor is None:
        return None
    line = next((ev for ev in shot["events"] if ev["kind"] == "line" and ev["id"] == anchor["line"]), None)
    if line is None:
        raise refuse(f"The anchor names no line of shot {sid}: {anchor['line']}", "Anchor to a line of this shot",
                     ids=[ev["id"] for ev in layout.lines_of(shot)])
    return line[f"{anchor['at']}_ms"]


def _settle(before: dict, script: dict, ev: dict | None, how: str, pace: float | None) -> dict:
    """The script timed again from `before` and checked (`timing.retime`); -> the moves `timing.retime` reports."""
    return timing.retime(before, script, ev, how, pace)[1]


def settle(script: dict, counters: dict, pace: float | None, moved: dict | None,
           before: dict | None = None) -> tuple[list[str], dict | None, list[str]]:
    """On a tool's write: the keyframes filled, each its next `p` id; then, with `before` the file as read, `hold`
    until it changes nothing, the script timed and filled again after each change.
    -> (ids, moves, the did-line notes)."""
    def new_id() -> str:
        return next_id(script, counters, "p")

    added, moves = keys.settle(script, new_id, pace, moved)
    said: list[str] = []
    for _ in range(sum(ev["kind"] == "pose" for shot in layout.shots(script) for ev in shot["events"]) + 1):
        was, held = copy.deepcopy(script), {}
        if before is None or not hold.hold(script, before, held, said):
            break
        moves = moves or {"events": {}, "shots": {}}
        for part, more in timing.retime(was, script, None, "fill", pace)[1].items():   # names `held`'s moves too
            for k, by in more.items():
                moves[part][k] = moves[part].get(k, 0) + by
        more_added, moves = keys.settle(script, new_id, pace, moves)
        added += more_added
    return added, moves, said


def _done(ev: dict, shot: dict, verb: str = "", tail: str = "") -> dict:
    """The did-line: the event's time in its shot and in the script."""
    who = ev.get("speaker") or ev.get("character") or ev.get("cue")
    when = clock.span(shot, ev["start_ms"], ev["end_ms"])
    return {"did": f"{verb}{ev['kind']} {ev['id']} · {who} · shot {shot['id']} · {when}{tail}", "shot": shot,
            "acted": ev["id"]}


# ---------------------------------------------------------------- events
def line_add(script: dict, counters: dict, args: dict, pace: float | None = None) -> dict:
    before = copy.deepcopy(script)
    n, shot = find_shot(script, args["shot"])
    speaker = _member(script, n, args["speaker"], "line")
    start = layout.last_line_end(shot)
    held = {**layout.voice(script, pace), **{k: args[k] for k in ("language", "emotion", "pace") if k in args}}
    ev = {"id": next_id(script, counters, "l"), "kind": "line", "start_ms": start,       # the pace alone
          "end_ms": start + layout.line_ms(args["words"], held["pace"]), "speaker": speaker, "words": args["words"],
          **held}
    shot["events"].append(ev)
    moved = _settle(before, script, ev, "add", pace)
    return {**_done(ev, shot), "scene": n, "moved": moved}


def cue_add(script: dict, counters: dict, args: dict, pace: float | None = None) -> dict:
    before = copy.deepcopy(script)
    n, shot = find_shot(script, args["shot"])
    at = _anchor(shot, args.get("anchor"), shot["id"])
    start = layout.last_line_end(shot) if at is None else at
    ev = {"id": next_id(script, counters, "c"), "kind": "cue", "start_ms": start, "end_ms": start + layout.CUE_MS,
          "cue": args["cue"], "words": args["words"], **({"anchor": dict(args["anchor"])} if "anchor" in args else {})}
    shot["events"].append(ev)
    moved = _settle(before, script, ev, "add", pace)
    return {**_done(ev, shot), "scene": n, "moved": moved}


def _pose_name(pose: str) -> str:
    if pose not in scriptshape.POSES:
        raise refuse(f"{pose} is not a pose", "Use one of the seven poses", valid_poses=list(scriptshape.POSES))
    return pose


def pose_add(script: dict, counters: dict, args: dict, pace: float | None = None) -> dict:
    before = copy.deepcopy(script)
    n, shot = find_shot(script, args["shot"])
    character = _member(script, n, args["character"], "pose")
    pose = _pose_name(args["pose"])
    if "anchor" in args and "start_ms" in args:
        raise refuse("A pose takes an anchor or a start_ms, not both", "Send one of them")
    at = _anchor(shot, args.get("anchor"), shot["id"])
    start = at if at is not None else shot["start_ms"] + args.get("start_ms", 0)
    anchor = dict(args["anchor"]) if "anchor" in args else None
    hit = keys.after_line(shot, character, start, anchor["line"] if anchor else None)
    if hit is not None:                            # at the speaker's run's end or inside, after it
        if hit[1] is None:
            raise timing.no_instant(shot, hit[0])
        start, anchor = hit[1], None
    ev = keys.at(shot, character, start)
    if ev is not None:                                   # one keyframe per instant, replaced
        old, ev["pose"] = ev["pose"], pose
        ev.pop("auto", None)                             # the Director's now
        touched, tail = [ev, *keys.follow(shot, ev, old)], f" · {pose} (replaced)"
    else:
        ev = {"id": next_id(script, counters, "p"), "kind": "pose", "start_ms": start, "end_ms": start + 1,
              "character": character, "pose": pose, **({"anchor": anchor} if anchor else {})}
        shot["events"].append(ev)
        touched, tail = [ev], ""
        if start > shot["start_ms"] + layout.LAST_POSE_MS:
            raise timing.outside(ev, shot)
    moved = _settle(before, script, ev, "add", pace)
    keys.check(script, shot, touched)
    return {**_done(ev, shot, "", tail), "scene": n, "moved": moved}


def _into(script: dict, n: int, home: dict, ev: dict, ident: str) -> dict:
    """The shot `ident` names, of the event's own scene; the event moved into it, a line with every
    event of its old shot anchored to it (each keeping its anchor, shifted with the line until the timing places it)."""
    m, shot = find_shot(script, ident)
    if m != n:
        raise refuse(f"Shot {shot['id']} is in scene {m}, {ev['id']} in scene {n}", f"Move it to a shot of scene {n}, "
                     f"or remove it and add it again in scene {m}",
                     shots=[s.get("id") for s in script["scenes"][n - 1]["shots"]])
    if shot is not home:
        along = [e for e in home["events"] if ev["kind"] == "line" and e.get("anchor", {}).get("line") == ev["id"]]
        for e in (ev, *along):
            home["events"].remove(e)
            shot["events"].append(e)
    return shot


def event_move(script: dict, args: dict, pace: float | None = None) -> dict:
    """An event to start `start_ms` after the start of its shot, or of the named shot of its scene; a
    line keeps its length and its anchored events follow it; a moved cue or pose is no longer anchored; the events
    behind it on its row are pushed."""
    before = copy.deepcopy(script)
    n, home, ev = find_event(script, args["id"])
    shot = _into(script, n, home, ev, args["shot"]) if "shot" in args else home
    length = ev["end_ms"] - ev["start_ms"]
    ev.pop("anchor", None)
    ev.pop("auto", None)                                 # a moved pose is the Director's
    start = shot["start_ms"] + args["start_ms"]
    hit = keys.after_line(shot, ev["character"], start) if ev["kind"] == "pose" else None
    if hit is not None:                             # keyed after the speaker's line, as `pose_add` keys it
        if hit[1] is None:
            raise timing.no_instant(shot, hit[0])        # no instant left after the run
        start = hit[1]
    for e in (e for e in shot["events"] if shot is not home and e.get("anchor", {}).get("line") == ev["id"]):
        e["start_ms"], e["end_ms"] = e["start_ms"] + start - ev["start_ms"], e["end_ms"] + start - ev["start_ms"]
    ev["start_ms"], ev["end_ms"] = start, start + (length if ev["kind"] != "pose" else 1)
    if ev["kind"] == "pose" and ev["start_ms"] > shot["start_ms"] + layout.LAST_POSE_MS:
        raise timing.outside(ev, shot)
    if ev["kind"] == "pose":                             # before the timing's "starts with"
        keys.check(script, shot, [ev])
    moved = _settle(before, script, ev, "move", pace)
    if ev["kind"] == "pose":
        keys.check(script, shot, [ev])
    return {**_done(ev, shot, "moved ", "" if shot is home else f" · from {home['id']}"), "scene": n, "moved": moved}


def _field(kind: str, key: str, value: Any) -> Any:
    bad = refuse(f"{key} of a {kind} cannot be {value!r}", "Send a value the field takes", fields=list(FIELDS[kind]))
    if key in ("words", "language", "emotion"):          # text, not blank, any length
        if not isinstance(value, str) or not value.strip():
            raise bad
    elif key in ("pace", "seconds"):                     # any number above 0
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not value > 0:
            raise bad
    elif key == "cue" and value not in scriptshape.CUES:
        raise bad
    elif key == "pose":
        return _pose_name(value) if isinstance(value, str) else _pose_name(str(value))
    return value


def event_change(script: dict, args: dict, pace: float | None = None) -> dict:
    """A line's words, language, emotion, pace (its length again); a cue's cue, words, seconds; a pose's pose."""
    before = copy.deepcopy(script)
    n, shot, ev = find_event(script, args["id"])
    kind, fields, old = ev["kind"], args["fields"], ev.get("pose")
    wrong = [k for k in fields if k not in FIELDS[kind]]
    if wrong or not fields:
        raise refuse(f"A {kind} has no field {wrong[0]}" if wrong else "No field to change",
                     f"Change only the fields of a {kind}", fields=list(FIELDS[kind]))
    for key, value in fields.items():
        value = _field(kind, key, value)
        if key == "seconds":
            ev["end_ms"] = ev["start_ms"] + round(value * 1000)
        else:
            ev[key] = value
    ev.pop("auto", None)                                 # a pose changed is the Director's
    if kind == "line":
        ev["end_ms"] = ev["start_ms"] + layout.line_ms(ev["words"], ev.get("pace") or pace)
    touched = [ev, *keys.follow(shot, ev, str(old))] if kind == "pose" and ev["pose"] != old else []
    moved = _settle(before, script, ev, "change", pace)
    keys.check(script, shot, touched)
    return {**_done(ev, shot, "changed "), "scene": n, "moved": moved}

