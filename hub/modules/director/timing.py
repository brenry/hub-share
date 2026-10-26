"""Timing (blueprint A.4; R48 §3), pure: after every change the whole script is timed again from the
file as it was before the change and the file with the change applied, shot by shot, in offsets from each shot's
start. Inside a shot two rows push: the lines (every speaker's together, one speaker at a time) and the cues; poses do
not push, each holds until the character's next pose. On a row an event that sat right behind the one before it
follows it (a lengthened line pushes it by exactly the overrun, a shortened one pulls it back); one that did not keeps
its start, a pause the Director made, unless the event before it now runs into it; a cue put after a line follows
that line. An anchored event starts at its line, a moved one where the call says; either one that would start inside
the event before it is refused. A line lasts its words at its own pace, else the Hub's, plus the turn pause.
Then the checks (`check_shot`): one Ref2VA pass per shot, no pose inside its character's own line (no most seconds
per scene).
"""
from __future__ import annotations

from typing import Any

from hub.core.api import Invalid

from . import clock, layout
from .layout import refuse, secs, secs_up


def _offsets(shot: dict) -> dict[str, tuple[int, int]]:
    return {ev["id"]: (ev["start_ms"] - shot["start_ms"], ev["end_ms"] - shot["start_ms"]) for ev in shot["events"]}


def _abs(shot_start: int, at: int) -> int:
    return shot_start + at


def _inside(ev: dict, prev: dict, start: int, where: dict) -> Invalid:
    """A moved or anchored event that would start inside the event before it on its row; `where` the shot as it
    is timed (`id`, `start_ms`, and `home`: the shot the event was in before the call), the hint an offset in it,
    the shot named in the fix when the event comes from another."""
    hint = clock.hints(where, suggested_start_ms=start, **({} if ev["id"] == where.get("acted") else {"id": ev["id"]}))
    if ev["kind"] == "line":                       # a move onto the line before is refused
        return refuse(f"Line {ev['id']} would overlap line {prev['id']}", "Move it where no other line of the shot "
                      "is: one speaker at a time", **hint)
    if "anchor" in ev:
        return refuse(f"{ev['id']} would start inside {prev['id']}", "Remove its anchor, or move the cue before it",
                      **hint)
    other = "" if where["home"] == where["id"] else f" in shot {where['id']}"
    return refuse(f"{ev['id']} would start inside {prev['id']}",
                  f"event_move {ev['id']} to {secs_up(clock.rel(where, start))} s or later{other}", **hint)


def _row(row: list[dict], at: dict, was: dict, new: dict, moved: str | None, where: dict, length: Any,
         lines: list[dict], gone: frozenset = frozenset()) -> None:
    """One row timed in place into `new` {id: (start, end)}, offsets from the shot's start. An event of `gone`
    (in the shot before the call, not now) is timed as shortened to nothing, never fixed, and so pulls
    back what sat right behind it."""
    prev: dict | None = None
    for ev in row:
        i, here = ev["id"], at[ev["id"]][0]
        anchor = None if i in gone else ev.get("anchor")
        fixed = True
        if anchor and anchor["line"] in new:
            start = new[anchor["line"]][0 if anchor["at"] == "start" else 1]
        elif i == moved and i not in gone:
            start = here
        else:
            fixed = False
            after_prev = prev is not None and here == was.get(prev["id"], at[prev["id"]])[1]
            behind = next((ln for ln in lines if ln["id"] in was and was[ln["id"]][1] == here), None)
            if after_prev and prev is not None:
                start = new[prev["id"]][1]
            elif ev["kind"] == "cue" and behind is not None:
                start = new[behind["id"]][1]
            else:
                start = here
        if prev is not None and start < new[prev["id"]][1]:
            if fixed:
                raise _inside(ev, prev, _abs(where["start_ms"], new[prev["id"]][1]), where)
            start = new[prev["id"]][1]
        new[i] = (start, start + length(ev))
        prev = ev


def holding_open(events: list[dict], start: Any) -> list[dict]:
    """The poses whose second holds a shot open, `start(ev)` each one's start. A keyframe anchored to a
    line that repeats its character's keyframe before it in the shot (the Hub's fill, or a follower) changes nothing
    and holds nothing open; every other pose does (the Director's)."""
    poses = sorted((ev for ev in events if ev["kind"] == "pose"), key=start)
    out = []
    for ev in poses:
        prior = [p for p in poses if p["character"].casefold() == ev["character"].casefold() and start(p) < start(ev)]
        if not ("anchor" in ev and prior and prior[-1]["pose"] == ev["pose"]):
            out.append(ev)
    return out


def _content_end(events: list[dict], new: dict) -> int:
    ends = [new[ev["id"]][1] for ev in events if ev["kind"] != "pose"]
    ends += [min(new[ev["id"]][0] + layout.POSE_MIN_MS, layout.SHOT_MAX_MS)
             for ev in holding_open(events, lambda ev: new[ev["id"]][0])]
    return max([layout.SHOT_MIN_MS, *ends])


def _shot(shot: dict, start: int, old: dict | None, moved: str | None, pace: float | None, home: Any = None,
          acted: str | None = None) -> None:
    """The shot timed again, in place, starting at `start`; `home` the shot id the moved event was in before, `acted`
    the call's event (a refusal naming another carries its `id`)."""
    events = shot["events"]
    at, was = _offsets(shot), (_offsets(old) if old is not None else {})
    gone = [ev for ev in (old["events"] if old is not None else []) if ev["id"] not in at and ev["kind"] != "pose"]
    ghosts = frozenset(ev["id"] for ev in gone)          # removed, or moved into another shot
    at = {**{i: was[i] for i in ghosts}, **at}
    order = {ev["id"]: n for n, ev in enumerate(events)}

    def row(kind: str) -> list[dict]:
        return sorted((ev for ev in [*events, *gone] if ev["kind"] == kind),
                      key=lambda ev: (at[ev["id"]][0], order.get(ev["id"], -1)))

    def length(ev: dict) -> int:
        if ev["id"] in ghosts:
            return 0
        if ev["kind"] == "line":
            return layout.line_ms(ev["words"], ev.get("pace") or pace)
        return at[ev["id"]][1] - at[ev["id"]][0]

    new: dict[str, tuple[int, int]] = {}
    lines = row("line")
    where = {"id": shot.get("id"), "start_ms": start, "home": home, "acted": acted}
    _row(lines, at, was, new, moved, where, length, [], ghosts)
    _row(row("cue"), at, was, new, moved, where, length, lines, ghosts)
    for i in ghosts:
        del new[i]
    for ev in row("pose"):
        anchor = ev.get("anchor")
        here = new[anchor["line"]][0 if anchor["at"] == "start" else 1] if anchor and anchor["line"] in new \
            else at[ev["id"]][0]
        new[ev["id"]] = (here, here + 1)
    same = old is not None and set(was) == set(new) and all(
        new[i][0] == was[i][0] and (ev["kind"] == "pose" or new[i][1] == was[i][1])
        for i, ev in ((e["id"], e) for e in events))
    kept = same and old is not None and not layout.hold_ms(old) and not layout.hold_ms(shot)
    span = old["end_ms"] - old["start_ms"] if kept and old is not None else \
        max(layout.hold_ms(shot), _content_end(events, new))
    shot["start_ms"], shot["end_ms"] = start, start + span
    for ev in events:
        ev["start_ms"], ev["end_ms"] = start + new[ev["id"]][0], start + new[ev["id"]][1]
    poses = sorted((ev for ev in events if ev["kind"] == "pose"), key=lambda ev: ev["start_ms"])
    for n, ev in enumerate(poses):
        later = [p["start_ms"] for p in poses[n + 1:]
                 if p["character"].casefold() == ev["character"].casefold() and p["start_ms"] > ev["start_ms"]]
        ev["end_ms"] = later[0] if later else shot["end_ms"]


def outside(ev: dict, shot: dict, other: bool = False) -> Invalid:
    """The hint `latest_start_ms` a start that lands (a pose's `LAST_POSE_MS`, a cue's or a line's the
    pass less its length); `other`: not the call's event, its `id` named."""
    length = ev["end_ms"] - ev["start_ms"]
    latest = layout.LAST_POSE_MS if ev["kind"] == "pose" else max(0, layout.SHOT_MAX_MS - length)
    return refuse(f"{ev['kind'].capitalize()} {ev['id']} would fall outside shot {shot['id']}'s "
                  f"{secs(layout.SHOT_MAX_MS)} s", "Place it inside the shot: start it at latest_start_ms or earlier",
                  **clock.hints(shot, shot_max_end_ms=shot["start_ms"] + layout.SHOT_MAX_MS,
                                latest_start_ms=shot["start_ms"] + latest, **({"id": ev["id"]} if other else {})))


def past(shot: dict, acted: dict | None, how: str) -> dict:
    """Who an overrun names: the call's event when the call moved or added it, else the event that ends
    past the pass (a pose holding the shot open when none does)."""
    if acted is not None and how in ("add", "move"):
        return acted
    cap = shot["start_ms"] + layout.SHOT_MAX_MS
    over = [ev for ev in shot["events"] if ev["kind"] != "pose" and ev["end_ms"] > cap]
    return max(over, key=lambda ev: ev["end_ms"]) if over else acted or max(shot["events"], key=lambda e: e["start_ms"])


def no_instant(shot: dict, line: dict) -> Invalid:
    """A pose asked at the end of (or inside) a speaker's run of lines with no instant left after it."""
    return refuse(f"No instant is left after {line['speaker']}'s line {line['id']} in shot {shot['id']}", NO_AFTER,
                  **clock.hints(shot, line=line["id"], end_ms=line["end_ms"]))


def run_end(shot: dict, line: dict) -> int:
    """The end of the run holding `line`: the speaker's lines, each starting at the one before's end."""
    end, mine = line["end_ms"], [ln for ln in layout.lines_of(shot)
                                 if ln["speaker"].casefold() == line["speaker"].casefold()]
    while (nxt := next((ln for ln in mine if ln["start_ms"] == end and ln["end_ms"] > end), None)) is not None:
        end = nxt["end_ms"]
    return end


NO_AFTER = "Set it at the line's start, or in the next shot"   # no instant after the line is left


def after_ms(shot: dict, line: dict) -> int | None:
    """The run's last end + 500 ms, again past each of the speaker's lines it would fall
    in; None when that is after the shot's last pose start."""
    mine = [ln for ln in layout.lines_of(shot) if ln["speaker"].casefold() == line["speaker"].casefold()]
    ms = run_end(shot, line) + layout.AFTER_LINE_MS
    while (hit := next((ln for ln in mine if ln["start_ms"] <= ms <= ln["end_ms"]), None)) is not None:
        ms = run_end(shot, hit) + layout.AFTER_LINE_MS
    return ms if ms <= shot["start_ms"] + layout.LAST_POSE_MS else None


def after(pose: dict, acted: dict | None, line: dict, shot: dict) -> dict:
    """A line grown past a pose that stays put is refused with the hint `after_ms` (`after_ms` of the line)."""
    ms = None if acted is pose else after_ms(shot, line)
    return {} if ms is None else {"after_ms": ms}


def check_shot(shot: dict, acted: dict | None, how: str, pace: float | None = None) -> None:
    """The checks of a shot as timed: within one pass, no pose inside its own line, no two poses at once."""
    cap = shot["start_ms"] + layout.SHOT_MAX_MS
    if acted is not None and acted["start_ms"] < shot["start_ms"]:
        raise outside(acted, shot)
    if shot["end_ms"] > cap:
        if acted is not None and acted["kind"] == "line" and how in ("add", "change"):
            room = cap - acted["start_ms"] - max(0, shot["end_ms"] - acted["end_ms"])
            raise refuse(f"Line {acted['id']} would carry shot {shot['id']} past {secs(layout.SHOT_MAX_MS)} s",
                         "Split the words across two shots: shot_add, then line_add the rest there",
                         **clock.hints(shot, max_words=layout.max_words(room, acted.get("pace") or pace),
                                       suggested_end_ms=cap))
        if acted is not None and acted["kind"] == "cue" and how == "change":       # its seconds
            room = cap - acted["start_ms"] - max(0, shot["end_ms"] - acted["end_ms"])
            raise refuse(f"Cue {acted['id']} at {secs(acted['end_ms'] - acted['start_ms'])} s would carry shot "
                         f"{shot['id']} past {secs(layout.SHOT_MAX_MS)} s", "Give it at most max_seconds",
                         **clock.hints(shot, max_seconds=max(0, room) // 100 / 10, suggested_end_ms=cap))
        named = past(shot, acted, how)
        raise outside(named, shot, named is not acted)
    lines = layout.lines_of(shot)
    poses = [ev for ev in shot["events"] if ev["kind"] == "pose" and not ev.get("auto")]
    for p in poses:
        for line in lines:
            if line["speaker"].casefold() == p["character"].casefold() and \
                    line["start_ms"] < p["start_ms"] < line["end_ms"]:
                if acted is p and after_ms(shot, line) is None:
                    raise no_instant(shot, line)
                later = after(p, acted, line, shot)
                raise refuse(f"Pose {p['id']} of {p['character']} starts inside {p['character']}'s own line "
                             f"{line['id']}", "Anchor it to that line's start, or give it a start_ms after the line's "
                             "end" if later or acted is p else NO_AFTER,
                             **clock.hints(shot, line=line["id"], start_ms=line["start_ms"], end_ms=line["end_ms"],
                                           **later, **({} if acted is p else {"id": p["id"]})))
        for q in poses:
            if q is not p and q["character"].casefold() == p["character"].casefold() and \
                    q["start_ms"] == p["start_ms"] and q["pose"] != p["pose"]:   # the same pose: one
                mover, other = (p, q) if acted is p else (q, p)
                raise refuse(f"Pose {mover['id']} starts with pose {other['id']} of {p['character']}",
                             f"Change pose {other['id']} with event_change, or start this one elsewhere",
                             ids=[other["id"]])


def _by_id(script: dict) -> dict[Any, dict]:
    """Shots by id; a shot without one (a file written without shot ids) by its place."""
    return {shot.get("id") or n: shot for n, shot in enumerate(layout.shots(script))}


def _moves(before: dict, after: dict, named: str | None) -> dict:
    """{events: {id: ms}, shots: {id: ms}}: events moved inside their shot, other than the one named; shots moved."""
    was = _by_id(before)
    events: dict[str, int] = {}
    shots: dict[str, int] = {}
    for n, shot in enumerate(layout.shots(after)):
        old = was.get(shot.get("id") or n)
        if old is None:
            continue
        if shot["start_ms"] != old["start_ms"]:
            shots[shot.get("id") or f"shot {n + 1}"] = shot["start_ms"] - old["start_ms"]
        then, now = _offsets(old), _offsets(shot)
        for i, (start, _end) in now.items():
            if i != named and i in then and start != then[i][0]:
                events[i] = start - then[i][0]
    return {"events": events, "shots": shots}


def retime(before: dict, after: dict, acted: dict | None = None, how: str = "",
           pace: float | None = None) -> tuple[dict, dict]:
    """`after` timed again in place from `before`, then checked (`check_shot`). `acted` is the event the call named,
    `how` what it did ("add", "move", "change", "remove"); `pace` the Hub's (None: the engine's 2.6).
    -> (after, the moves `_moves` names)."""
    was = _by_id(before)
    moved = acted["id"] if acted is not None and how == "move" else None
    home = next((shot.get("id") for shot in layout.shots(before) for ev in shot["events"]
                 if moved is not None and ev["id"] == moved), None)
    start = 0
    for n, shot in enumerate(layout.shots(after)):
        _shot(shot, start, was.get(shot.get("id") or n), moved, pace, home, acted["id"] if acted else None)
        start = shot["end_ms"]
    for shot in layout.shots(after):
        mine = acted is not None and any(ev is acted for ev in shot["events"])
        check_shot(shot, acted if mine else None, how, pace)
    return after, _moves(before, after, acted["id"] if acted is not None else None)
