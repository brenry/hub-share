"""Pose keyframes (blueprint A.5; R48 §2, §8), pure. A keyframe is a pose event's start: at that
instant its character is in that pose, and its pose in force at an instant is its latest keyframe at or before it in
the shot. One keyframe per character per instant. `fill` adds the keyframes A.5 requires and the Hub makes certain of
(each cast member's at a shot's start, a speaker's at each of the speaker's lines' start and end), never changing one
that is there; `follow` gives a speaker's line-end keyframes a changed start pose; `check` refuses a speaker moving
while the speaker speaks for the keyframes a call set or changed; `holding` and `required` rule on removals. A pose
asked at the speaker's own line's end is keyed `AFTER_MS` after it (`after_line`): the keyframe at a speaker's line
end always holds the speaker's line-start pose. A keyframe the Hub fills carries `auto` and is worked out again on
every write (`settle`, `refresh`); a speaker's back-to-back lines are one run (`runs`), a pose asked at its end or
inside it keyed after the run.
"""
from __future__ import annotations

import copy
from typing import Any

from . import clock, layout, timing
from .layout import refuse, secs_up

DEFAULT = "stand"
AFTER_MS = layout.AFTER_LINE_MS   # a pose asked at a speaker's own line end is keyed this long after it


def _same(a: str, b: str) -> bool:
    return a.casefold() == b.casefold()


def keyframes(shot: dict, who: str) -> list[dict]:
    """The character's keyframes in the shot, by time."""
    return sorted((ev for ev in shot["events"] if ev["kind"] == "pose" and _same(ev["character"], who)),
                  key=lambda ev: ev["start_ms"])


def at(shot: dict, who: str, ms: int) -> dict | None:
    """The character's keyframe at that instant, if any."""
    return next((ev for ev in keyframes(shot, who) if ev["start_ms"] == ms), None)


def before(shot: dict, who: str, ms: int, strict: bool = False) -> dict | None:
    """The character's latest keyframe at (or, `strict`, before) that instant in the shot."""
    found = [ev for ev in keyframes(shot, who) if ev["start_ms"] < ms or (not strict and ev["start_ms"] == ms)]
    return found[-1] if found else None


def _scene_of(script: dict, shot: dict) -> dict:
    return next(sc for sc in script["scenes"] if any(s is shot for s in sc["shots"]))


def opening(script: dict, shot: dict, who: str) -> str:
    """Its pose at a shot's start: in force at the end of the scene's shot before (else earlier), else stand."""
    shots = _scene_of(script, shot)["shots"]
    for earlier in reversed(shots[:next(n for n, s in enumerate(shots) if s is shot)]):
        last = keyframes(earlier, who)
        if last:
            return str(last[-1]["pose"])
    return DEFAULT


def in_force(script: dict, shot: dict, who: str, ms: int, strict: bool = False) -> str:
    """A character's pose in force at that instant (just before it, `strict`), its opening pose before its first
    keyframe."""
    kf = before(shot, who, ms, strict)
    return str(kf["pose"]) if kf is not None else opening(script, shot, who)


def holds(shot: dict) -> None:
    """Each pose holds until the same character's next keyframe in the shot, else the shot's end."""
    poses = sorted((ev for ev in shot["events"] if ev["kind"] == "pose"), key=lambda ev: ev["start_ms"])
    for n, ev in enumerate(poses):
        later = [p["start_ms"] for p in poses[n + 1:]
                 if _same(p["character"], ev["character"]) and p["start_ms"] > ev["start_ms"]]
        ev["end_ms"] = later[0] if later else shot["end_ms"]


def fill(script: dict, new_id: Any, old: dict | None = None) -> list[str]:
    """The keyframes A.5 requires added where missing, each marked `auto`; one at the shot,
    character and instant of a keyframe `unfill` took out keeps its id (`old`), every other gets `new_id()`; -> the
    ids given anew. Filling a filled script adds nothing."""
    added: list[str] = []
    old = {} if old is None else old
    here = {ev["id"] for shot in layout.shots(script) for ev in shot["events"]}

    def add(shot: dict, who: str, ms: int, pose: str, anchor: dict | None = None) -> None:
        kept = old.pop((id(shot), who.casefold(), ms), None)
        ident = kept if kept is not None and kept not in here else new_id()
        ev = {"id": ident, "kind": "pose", "start_ms": ms, "end_ms": ms + 1, "character": who, "pose": pose,
              **({"anchor": anchor} if anchor else {}), "auto": True}
        shot["events"].append(ev)
        here.add(ident)
        if ident != kept:
            added.append(ident)

    for sc in script["scenes"]:
        for shot in sc["shots"]:
            for who in sc["cast"]:
                if at(shot, who, shot["start_ms"]) is None:
                    add(shot, who, shot["start_ms"], opening(script, shot, who))
            for line in layout.lines_of(shot):
                who = line["speaker"]
                if at(shot, who, line["start_ms"]) is None:
                    add(shot, who, line["start_ms"], in_force(script, shot, who, line["start_ms"]),
                        {"line": line["id"], "at": "start"})
                if not _closes(shot, line) and at(shot, who, line["end_ms"]) is None:
                    start = at(shot, who, line["start_ms"])
                    add(shot, who, line["end_ms"], str(start["pose"]) if start else DEFAULT,
                        {"line": line["id"], "at": "end"})
            holds(shot)
    return added


def unfill(script: dict) -> dict[tuple[int, str, int], str]:
    """Every `auto` keyframe taken out; -> {(shot, folded character, instant): its id}."""
    out: dict[tuple[int, str, int], str] = {}
    for shot in layout.shots(script):
        for ev in [e for e in shot["events"] if e["kind"] == "pose" and e.get("auto")]:
            out[(id(shot), ev["character"].casefold(), ev["start_ms"])] = ev["id"]
            shot["events"].remove(ev)
    return out


def rework(script: dict, new_id: Any) -> list[str]:
    """The `auto` keyframes taken out and filled again; one that keeps its id keeps its place among the
    shot's events too. -> the ids given anew."""
    places = {ev["id"]: n for shot in layout.shots(script) for n, ev in enumerate(shot["events"]) if ev.get("auto")}
    added = fill(script, new_id, unfill(script))
    for shot in layout.shots(script):
        back = sorted((places[ev["id"]], ev) for ev in shot["events"] if ev.get("auto") and ev["id"] in places
                      and ev["id"] not in added)
        for n, ev in back:
            shot["events"].remove(ev)
            shot["events"].insert(n, ev)
    return added


def refresh(script: dict) -> None:
    """Inside a call, before its checks: each `auto` keyframe, in place, in the pose in force just
    before its instant (the character's opening pose at a shot's start), in script order."""
    for sc in script["scenes"]:
        for shot in sc["shots"]:
            for ev in sorted((e for e in shot["events"] if e["kind"] == "pose" and e.get("auto")),
                             key=lambda e: e["start_ms"]):
                who = ev["character"]
                ev["pose"] = opening(script, shot, who) if ev["start_ms"] == shot["start_ms"] else \
                    in_force(script, shot, who, ev["start_ms"], strict=True)


def _autos(script: dict) -> list[tuple]:
    return sorted((ev["id"], n, ev["character"], ev["start_ms"], ev["pose"])
                  for n, shot in enumerate(layout.shots(script)) for ev in shot["events"]
                  if ev["kind"] == "pose" and ev.get("auto"))


def _closes(shot: dict, line: dict) -> bool:
    """Nothing else in the shot (a line, a cue, a Director's pose's second) ends after the line: the pose
    in force at its end is held to the shot's end, and no keyframe is filled there (a line ending the pass too)."""
    cap = shot["start_ms"] + layout.SHOT_MAX_MS
    ends = [ev["end_ms"] for ev in shot["events"] if ev["kind"] != "pose" and ev is not line]
    ends += [min(p["start_ms"] + layout.POSE_MIN_MS, cap)
             for p in timing.holding_open(shot["events"], lambda ev: ev["start_ms"])]
    return all(end <= line["end_ms"] for end in ends)


def merge(script: dict) -> None:
    """Two keyframes of one character timed to one instant in the same pose (a line's end keyframe and the next
    line's start keyframe, brought together by a move) are one: the later of them is dropped. A keyframe that holds
    nothing open left at its shot's end instant (a line's end keyframe when what ran after the line went) is dropped
    too: that line now closes the shot, and no event starts at its shot's end."""
    for shot in layout.shots(script):
        open_ = timing.holding_open(shot["events"], lambda ev: ev["start_ms"])
        for ev in [e for e in shot["events"] if e["kind"] == "pose" and e["start_ms"] >= shot["end_ms"]]:
            if not any(ev is p for p in open_):
                shot["events"].remove(ev)
        seen: dict[tuple[str, int], dict] = {}
        for ev in [e for e in shot["events"] if e["kind"] == "pose"]:
            key = (ev["character"].casefold(), ev["start_ms"])
            if key in seen and seen[key]["pose"] == ev["pose"]:
                if seen[key].get("auto") and not ev.get("auto"):    # the Director's is kept
                    seen[key], ev = ev, seen[key]
                shot["events"].remove(ev)
            else:
                seen.setdefault(key, ev)


def settle(script: dict, new_id: Any, pace: float | None, moves: dict | None) -> tuple[list[str], dict | None]:
    """`fill` on a tool's write, every `auto` keyframe worked out again first, the script timed again
    when any keyframe changed (a keyframe holds a second): -> (the ids added, the call's moves with the ones
    this timing made)."""
    was = copy.deepcopy(script)
    then = _autos(script)
    merge(script)
    added = rework(script, new_id)
    here = {ev["id"] for shot in layout.shots(script) for ev in shot["events"]}
    out = {"events": {k: by for k, by in (moves or {}).get("events", {}).items() if k in here},
           "shots": dict((moves or {}).get("shots", {}))}
    if not added and _autos(script) == then:
        return added, out if moves is not None else None
    more = timing.retime(was, script, None, "fill", pace)[1]
    merge(script)                                        # a shot this timing ended at a pose holding nothing open
    for part in ("events", "shots"):
        for k, by in more[part].items():
            out[part][k] = out[part].get(k, 0) + by
    return added, out


def follow(shot: dict, kf: dict, old: str) -> list[dict]:
    """The speaker's keyframe at the end of each of the speaker's lines that starts at `kf`, when it held the old
    pose, takes the new one. -> the keyframes changed."""
    changed = []
    for line in layout.lines_of(shot):
        if _same(line["speaker"], kf["character"]) and line["start_ms"] == kf["start_ms"]:
            end = at(shot, kf["character"], line["end_ms"])
            if end is not None and end is not kf and end["pose"] == old:
                end["pose"] = kf["pose"]
                changed.append(end)
    return changed


def runs(shot: dict, who: str) -> list[list[dict]]:
    """A speaker's lines in the shot by time, in runs; a line starting at the one before's end is in it."""
    out: list[list[dict]] = []
    for ln in sorted((ln for ln in layout.lines_of(shot) if _same(ln["speaker"], who)), key=lambda ln: ln["start_ms"]):
        if out and out[-1][-1]["end_ms"] == ln["start_ms"]:
            out[-1].append(ln)
        else:
            out.append([ln])
    return out


def after_line(shot: dict, who: str, ms: int, line_id: str | None = None) -> tuple[dict, int | None] | None:
    """When `ms` is the end of a run of the speaker's lines in the shot, or inside a run of two or
    more (`line_id`: the run holding that line of the speaker's only), (the run's last line, `timing.after_ms` of it:
    where a pose asked there is keyed, None when no instant is left); else None."""
    for run in runs(shot, who):
        if line_id is not None and not any(ln["id"] == line_id for ln in run):
            continue
        start, end = run[0]["start_ms"], run[-1]["end_ms"]
        if ms == end or (len(run) > 1 and start < ms < end):
            return run[-1], timing.after_ms(shot, run[-1])
    return None


def check(script: dict, shot: dict, touched: list[dict]) -> None:
    """A speaker's keyframe at a line's end in a pose other than the speaker's keyframe at that line's start, when
    the call set or changed either, is refused with the fix; a pair already in the file is drawn as written. The `auto`
    keyframes are worked out first. The line-end keyframe is never replaced by another pose; the hint's `after_ms` is
    the run's last end + `AFTER_MS`, where a pose is accepted as any."""
    refresh(script)
    ids = {id(kf) for kf in touched}
    for line in layout.lines_of(shot):
        who = line["speaker"]
        start = at(shot, who, line["start_ms"])
        ends = [kf for kf in keyframes(shot, who) if kf["start_ms"] == line["end_ms"]]
        for end in ends:
            if start is None or start["pose"] == end["pose"] or not {id(start), id(end)} & ids:
                continue
            raise moving(shot, line, start["pose"], end["pose"])


def moving(shot: dict, line: dict, was: str, now: str) -> Exception:
    """The refusal of `check`, its hint `after_ms` the run's last end + `AFTER_MS`, past the speaker's next
    lines and none when no instant is left; the fix's time rounded up."""
    later = timing.after(line, None, line, shot)
    fix = f"Give the new pose start_ms = after_ms ({secs_up(clock.rel(shot, later['after_ms']))} s, after those " \
        "lines), or set it at the line's start" if later else timing.NO_AFTER
    return refuse(f"{line['speaker']} would change from {was} to {now} while speaking {line['id']}", fix,
                  **clock.hints(shot, line=line["id"], start_pose=was, **later))


def holding(script: dict, shot: dict, line: dict) -> list[dict]:
    """The line's anchored keyframes that repeat the pose in force just before them (they change nothing)."""
    out = []
    for ev in sorted(shot["events"], key=lambda e: e["start_ms"]):
        if ev["kind"] == "pose" and ev.get("anchor", {}).get("line") == line["id"]:
            prior = before(shot, ev["character"], ev["start_ms"], strict=True)
            while prior is not None and prior in out:
                prior = before(shot, ev["character"], prior["start_ms"], strict=True)
            was = str(prior["pose"]) if prior is not None else opening(script, shot, ev["character"])
            if ev["pose"] == was:
                out.append(ev)
    return out


def required(script: dict, shot: dict, kf: dict) -> None:
    """A keyframe `fill` requires is refused for removal, with the call that changes it."""
    who, ms = kf["character"], kf["start_ms"]
    fix = f"Change it: event_change {{id: {kf['id']}, fields: {{pose}}}}"
    if ms == shot["start_ms"] and any(_same(who, c) for c in _scene_of(script, shot)["cast"]):
        raise refuse(f"{kf['id']} is {who}'s pose at the start of shot {shot['id']}", fix, required="shot start")
    for line in layout.lines_of(shot):
        if _same(line["speaker"], who):
            for end in ("start", "end"):
                if line[f"{end}_ms"] == ms:
                    raise refuse(f"{kf['id']} is {who}'s pose at the {end} of line {line['id']}", fix,
                                 required=f"line {end}")
