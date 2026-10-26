"""`event_remove`, pure: a line, cue or pose taken out, its did-line naming whose it was
(`removed Speaker 1's line l3 · shot s1`); a line takes its holding keyframes along, the time it held closes. An id
that names a shot removes it when it is empty (no
line, cue or Director's pose, `air.bare`; held or not): its `auto` keyframes go with it, its panels are
not put back (their cause is gone), the later shots move up; a shot with something in it is refused with what is in it.
"""
from __future__ import annotations

import copy

from . import air, edit, keys, timing
from .layout import refuse


def _whose(ev: dict) -> str:
    if ev["kind"] == "line":
        return f"{ev.get('speaker')}'s line"
    return f"the {ev.get('cue')} cue" if ev["kind"] == "cue" else f"{ev.get('character')}'s pose"


def _shot(script: dict, args: dict, pace: float | None) -> dict | None:
    """The empty shot `args["id"]` names taken out; None when the id names no shot."""
    found = next(((n, sc, shot) for n, sc in enumerate(script["scenes"], 1) for shot in sc["shots"]
                  if shot.get("id") == args["id"]), None)
    if found is None:
        return None
    n, scene, shot = found
    if not air.bare(shot):                             # a held shot with nothing in it too
        inside = sorted((ev for ev in shot["events"] if ev["kind"] in ("line", "cue")
                         or ev["kind"] == "pose" and not ev.get("auto")), key=lambda e: (e["start_ms"], e["id"]))
        ids = [ev["id"] for ev in inside]
        raise refuse(f"Shot {shot['id']} is not empty: {', '.join(ids)}",
                     "Remove or move what is in it first (event_remove, or event_move with shot)",
                     shot=shot["id"], ids=ids)
    before = copy.deepcopy(script)
    scene["shots"].remove(shot)
    moved = timing.retime(before, script, None, "remove", pace)[1]
    return {"did": f"removed shot {shot['id']} · scene {n}", "shot": None, "scene": n, "moved": moved}


def event_remove(script: dict, args: dict, pace: float | None = None) -> dict:
    gone = _shot(script, args, pace)
    if gone is not None:
        return gone
    before = copy.deepcopy(script)
    n, shot, ev = edit.find_event(script, args["id"])
    if ev.get("auto"):                                   # not refused; the write fills it again
        return {"did": f"{ev['id']} is the Hub's; filled again", "shot": shot, "scene": n, "acted": ev["id"],
                "moved": timing.retime(before, script, None, "remove", pace)[1]}
    if ev["kind"] == "pose":
        keys.required(script, shot, ev)
    taken = keys.holding(script, shot, ev) if ev["kind"] == "line" else []
    anchored = [e["id"] for e in shot["events"] if e.get("anchor", {}).get("line") == ev["id"]
                and not any(e is t for t in taken)]
    if anchored:
        raise refuse(f"Line {ev['id']} has events anchored to it", "Remove or move those first",
                     anchored=anchored)
    for e in (ev, *taken):
        shot["events"].remove(e)
    moved = timing.retime(before, script, None, "remove", pace)[1]
    along = f" · with {', '.join(e['id'] for e in taken)}" if taken else ""
    return {"did": f"removed {_whose(ev)} {ev['id']} · shot {shot['id']}{along}", "shot": shot, "scene": n,
            "acted": ev["id"], "moved": moved}

