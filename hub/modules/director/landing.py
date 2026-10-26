"""Every correction tried before it is sent (R48 §2), pure. A refusal's hints
hold facts and at most one correction, the value `correction`'s table sends back as a call; `land` keeps the one the
table names for the refused call (every other correction-valued hint is left out), tries its value with
`attempt(calls) -> bool` (the corrected call(s) run as a write is run, on a copy of the file as read, nothing written),
and when that is
refused tries every value in the correction's direction; the first accepted replaces the value (and the
time the fix names), none accepted leaves the correction out and the fix names the other way. A shot's
held seconds are never corrected (the Hub never sets a shot's length).
"""
from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from hub.core.api import Invalid

from . import air, camera, clock, edit, layout, panels, scriptshape, stale, timing
from .layout import secs_up

STARTS = ("latest_start_ms", "suggested_start_ms", "after_ms")
VALUED = (*STARTS, "max_words", "max_seconds", "anchor")       # the hints `correction` can turn into a call
WORDS_FIX = "Split the words across two shots: shot_add, then line_add the rest there"
SECONDS_FIX = "Move the cue earlier, or into another shot"
CUE_FIX = "Add it to another shot"
START_FIX = "Start it elsewhere in the shot, or in another shot"
Calls = list[tuple[str, dict]]


def _event(script: dict, ident: Any) -> tuple[dict, dict] | None:
    return next(((shot, ev) for shot in layout.shots(script) for ev in shot["events"] if ev["id"] == ident), None)


def _shot(script: dict, ident: Any) -> dict | None:
    return next((shot for shot in layout.shots(script) if shot.get("id") == ident), None)


def _start(name: str, args: dict, hints: dict, value: int) -> Calls:
    """Rows 1 and 4 of `correction`: the same call with `start_ms` = the value (`pose_add` without its anchor,
    `event_move` into the hint's shot)."""
    sent = {k: v for k, v in args.items() if k != "anchor"}
    sent["start_ms"] = value
    if name == "event_move":
        sent["shot"] = hints["shot"]
    return [(name, sent)]


def _words(script: dict, name: str, args: dict) -> list[str]:
    if name == "line_add":
        return str(args["words"]).split()
    words = args["fields"].get("words")
    if words is None:
        found = _event(script, args["id"])
        words = found[1].get("words", "") if found else ""
    return str(words).split()


def correction(name: str, args: dict, got: dict, script: dict) -> tuple[str, Callable[[Any], Calls]] | None:
    """The correction table: (the hint that is the refusal's correction, value -> the calls that send it back); None."""
    h, problem = got.get("hints", {}), str(got.get("problem", ""))
    if "max_words" in h and name in ("line_add", "event_change"):
        cut = _words(script, name, args)
        if name == "line_add":
            return "max_words", lambda n: [(name, {**args, "words": " ".join(cut[:n])})]
        return "max_words", lambda n: [(name, {**args, "fields": {**args["fields"], "words": " ".join(cut[:n])}})]
    if "max_seconds" in h and name == "event_change" and _shot(script, args.get("id")) is None:   # never a shot's
        return "max_seconds", lambda s: [(name, {**args, "fields": {**args["fields"], "seconds": s}})]
    if "anchor" in h and name == "cue_add":
        return "anchor", lambda a: [(name, {**args, "anchor": dict(a)})]
    key = next((k for k in ("after_ms", "suggested_start_ms") if k in h), None)
    if key is not None and "id" in h:                    # row 2: another event blocks the call
        return key, lambda v: [("event_move", {"id": h["id"], "start_ms": v, "shot": h["shot"]}), (name, args)]
    if key == "after_ms" and name == "event_change" and "pose" in args.get("fields", {}):
        found = _event(script, args["id"])               # row 3: the pose asked after the line, as pose_add
        who = found[1].get("character", "") if found else ""
        return key, lambda v: [("pose_add", {"shot": h["shot"], "character": who, "pose": args["fields"]["pose"],
                                             "start_ms": v})]
    if name in ("pose_add", "event_move"):
        key = next((k for k in STARTS if k in h), None)
        if key is None and "end_ms" in h and "id" not in h and "starts inside" in problem:
            key = "end_ms"                               # row 4: the line's end, keyed after the line
        if key is not None:
            return key, lambda v: _start(name, args, h, v)
    return None


def _length(script: dict, name: str, args: dict, hints: dict) -> int:
    """The length of the event a start is tried for: the blocking one (row 2), else the call's (a pose 1 ms)."""
    found = _event(script, hints["id"] if "id" in hints else args.get("id"))
    if name == "pose_add" and "id" not in hints or found is None or found[1]["kind"] == "pose":
        return 1
    return found[1]["end_ms"] - found[1]["start_ms"]


def _instants(script: dict, name: str, args: dict, hints: dict, key: str, first: int) -> list[int]:
    """The shot's event starts and ends, each ±1 ms, less the event's length, + 500 ms, and the shot's limits,
    nearest the first value first; `latest_start_ms` downward, the others upward."""
    shot, length = _shot(script, hints.get("shot")), _length(script, name, args, hints)
    base = [0, layout.LAST_POSE_MS, layout.SHOT_MAX_MS - length]
    if shot is not None:
        for ev in shot["events"]:
            base += [clock.rel(shot, ev["start_ms"]), clock.rel(shot, ev["end_ms"])]
    found = {c for b in base for c in (b, b - 1, b + 1, b - length, b + layout.AFTER_LINE_MS)}
    down = key == "latest_start_ms"
    found = {c for c in found if 0 <= c <= layout.SHOT_MAX_MS and (c <= first if down else c >= first)}
    return [first, *sorted(found - {first}, key=lambda c: (abs(c - first), c))]


def _anchors(script: dict, args: dict, first: dict) -> list[dict]:
    """The shot's line starts and ends from the asked instant on, then the earlier ones, nearest first."""
    shot = _shot(script, args.get("shot"))
    if shot is None:
        return [first]
    asked = layout.last_line_end(shot)
    if "anchor" in args:
        line = next((ln for ln in layout.lines_of(shot) if ln["id"] == args["anchor"].get("line")), None)
        asked = line[f"{args['anchor']['at']}_ms"] if line else asked
    every = [({"line": ln["id"], "at": at}, ln[f"{at}_ms"]) for ln in layout.lines_of(shot) for at in ("start", "end")]
    later = sorted((p for p in every if p[1] >= asked), key=lambda p: p[1])
    earlier = sorted((p for p in every if p[1] < asked), key=lambda p: -p[1])
    out = [first, *(a for a, _ in [*later, *earlier] if a != first and a != args.get("anchor"))]
    return out


def candidates(script: dict, name: str, args: dict, hints: dict, key: str) -> list[Any]:
    first = hints[key]
    if key == "max_words":
        return [n for n in range(int(first), 0, -1)] or [first]
    if key == "max_seconds":
        steps = int(round((float(first) - 0.5) * 10))
        return [first, *(round(float(first) - 0.1 * k, 1) for k in range(1, steps + 1))] if steps > 0 else [first]
    if key == "anchor":
        return _anchors(script, args, first)
    return _instants(script, name, args, hints, key, int(first))


def _other_way(key: str, name: str) -> str:
    if key in ("after_ms", "end_ms"):
        return timing.NO_AFTER
    return {"max_words": WORDS_FIX, "max_seconds": SECONDS_FIX, "anchor": CUE_FIX}.get(key, START_FIX)


def land(name: str, args: dict, got: dict, script: dict, attempt: Callable[[Calls], bool]) -> dict:
    """The correction tried on one refusal `got` of the call `name args`, `script` the file as read: -> the refusal
    as it is sent."""
    out = copy.deepcopy(got)
    hints = out.setdefault("hints", {})
    if name == "cue_add" and "id" not in hints and any(k in hints for k in STARTS):
        anchors = _anchors(script, args, None)[1:]       # `cue_add` takes no start, an anchor
        if anchors:
            hints["anchor"] = anchors[0]
        else:
            out["fix"] = CUE_FIX
    found = correction(name, args, out, script)
    key = found[0] if found else None
    for k in VALUED:
        if k != key and hints.pop(k, None) is not None and k in str(out.get("fix", "")):
            out["fix"] = CUE_FIX if name == "cue_add" else START_FIX     # the fix named a hint left out
    if found is None:
        return out
    calls, first = found[1], hints[key]
    for value in candidates(script, name, args, hints, key):
        if attempt(calls(value)):
            hints[key] = value
            if key in (*STARTS, "end_ms") and value != first:
                out["fix"] = str(out.get("fix", "")).replace(secs_up(int(first)), secs_up(int(value)))
            if key == "anchor" and out["fix"] == CUE_FIX:
                out["fix"] = f"cue_add it again with anchor {{line: {value['line']}, at: {value['at']}}}"
            return out
    hints.pop(key, None)
    out["fix"] = _other_way(key, name)
    return out


def mended(name: str, args: dict, got: dict, script: dict, attempt: Callable[[Calls], bool]) -> Calls | None:
    """The calls of the correction `land` accepted for the refusal `got` of `name args` (`script` the
    file as read, `attempt` as `land`'s); None when it accepted none (or the refusal holds no correction)."""
    out = land(name, args, got, script, attempt)
    found = correction(name, args, out, script)
    if found is None or found[0] not in out.get("hints", {}):
        return None
    sent = found[1](out["hints"][found[0]])
    return sent if attempt(sent) else None

def write(script: dict, counters: dict, characters: Any, fn: Callable[[dict, dict, dict], dict], pace: float) -> dict:
    """A tool's change of the script in memory (`tools._write`, and each try here): `fn`, the keyframes and the hold,
    no hole it makes, no most seconds and no range around a named length; panels taken out around it, a drawn one
    whose prompt changed marked stale; every text camera as its object."""
    taken = panels.take(script)                      # no edit, timing or keyframe function sees a panel
    prompts = stale.before(script, taken)            # each panel's prompt on the script as it was
    edit.ensure_shot_ids(script, counters)
    camera.objects(script)                           # a text camera as its object, on every write
    before = copy.deepcopy(script)                   # the file as read
    done = fn(script, counters, characters)
    done["keys"], done["moved"], said = edit.settle(script, counters, pace, done.get("moved"), before)
    if said:
        done["did"] += " · " + "; ".join(said)
    air.kept(before, script, done.get("acted"))      # no silence the call makes
    panels.put(script, taken)
    stale.mark(script, prompts)                      # a drawn panel whose prompt changed is stale
    return done


def attempts(base: dict, characters: Any, counters: dict, pace: float,
             edit_of: Callable[[str, dict], Callable[[dict, dict, dict], dict]]) -> Callable[[Calls], bool]:
    """`land`'s `attempt`: the calls run in turn as a write is run (and checked as `scripts.change` checks the file)
    on a copy of `base`, its counters copied; nothing written. -> whether every one was accepted."""
    def attempt(calls: Calls) -> bool:
        script, ids = copy.deepcopy(base), dict(counters)
        try:
            for tool, args in calls:
                write(script, ids, characters, edit_of(tool, args), pace)
                scriptshape.read(script, characters)
        except Invalid:
            return False
        return True
    return attempt
