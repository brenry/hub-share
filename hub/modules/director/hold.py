"""The file holds after every write, pure: in every shot, each
speaker's keyframes after the start of a run of the speaker's lines and at or before its last line's end hold the pose
of the speaker's keyframe at the run's start. One pass over the script as `keys.settle` left it, `before` the file as
read: a Director's keyframe there in another pose that echoed the run's start pose before the call takes the start pose
now (as `keys.follow` does, for a start changed by any path); any other is keyed at `timing.after_ms` of the run's last
line, unanchored (taken out when a Director's keyframe of the speaker's already stands there); no instant left refuses
the write. `edit.settle` runs the pass, times the script again and works the `auto` keyframes out again until it changes
nothing.
"""
from __future__ import annotations

from typing import Any

from . import clock, keys, layout, timing
from .layout import refuse


def _old_echo(before: dict, kf: dict, first: dict) -> bool:
    """Whether `kf` held, in the file as read, the pose in force at the start of the line `first` (by ids)."""
    old_kf = next((ev for shot in layout.shots(before) for ev in shot["events"] if ev["id"] == kf["id"]), None)
    where = next(((shot, ev) for shot in layout.shots(before) for ev in shot["events"] if ev["id"] == first["id"]),
                 None)
    if old_kf is None or where is None or old_kf["kind"] != "pose":
        return False
    shot, line = where
    return old_kf["pose"] == keys.in_force(before, shot, kf["character"], line["start_ms"])


def _stuck(shot: dict, kf: dict, last: dict, pose: str) -> Exception:
    return refuse(f"{kf['character']}'s pose {kf['id']} at the end of {last['id']} is not the pose at its start "
                  f"({pose}), and no instant is left after it in shot {shot['id']}",
                  f"event_move {kf['id']} into the next shot, or event_change it to {pose}",
                  **clock.hints(shot, line=last["id"], id=kf["id"], start_pose=pose))


def _run(shot: dict, who: str, run: list[dict], before: dict, moves: dict, said: list[str]) -> bool:
    start, end = run[0]["start_ms"], run[-1]["end_ms"]
    first = keys.at(shot, who, start)
    if first is None:
        return False
    for kf in keys.keyframes(shot, who):
        if kf.get("auto") or not start < kf["start_ms"] <= end or kf["pose"] == first["pose"]:
            continue
        if _old_echo(before, kf, run[0]):
            kf["pose"] = first["pose"]
            return True
        ms = timing.after_ms(shot, run[-1])
        if ms is None:
            raise _stuck(shot, kf, run[-1], str(first["pose"]))
        standing = next((ev for ev in keys.keyframes(shot, who) if ev["start_ms"] == ms and not ev.get("auto")
                         and ev is not kf), None)
        if standing is not None:                     # it would be in force for no time
            shot["events"].remove(kf)
            said.append(f"{kf['id']} taken out: {standing['id']} stands after {run[-1]['id']}")
            return True
        moves[kf["id"]] = moves.get(kf["id"], 0) + ms - kf["start_ms"]
        kf["start_ms"], kf["end_ms"] = ms, ms + 1
        kf.pop("anchor", None)
        return True
    return False


def hold(script: dict, before: dict, moves: dict, said: list[str]) -> bool:
    """One pass, in place; `moves` {id: ms} gains each keyframe keyed later, `said` the did-line notes.
    -> whether anything changed (one keyframe at a time; the caller works the file out again and asks again)."""
    for sc in script["scenes"]:
        for shot in sc["shots"]:
            speakers: list[Any] = []
            for ln in layout.lines_of(shot):
                if not any(ln["speaker"].casefold() == s.casefold() for s in speakers):
                    speakers.append(ln["speaker"])
            for who in speakers:
                for run in keys.runs(shot, who):
                    if _run(shot, who, run, before, moves, said):
                        return True
    return False
