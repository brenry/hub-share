"""The mix's placement (blueprint §12.4, §19.1; R54's `place.py`), pure: one planned -> placed map
for the whole script, from the rows alone (no shot is read for sound), and every row's time in the track
(`measured`). And the file's checks of what the mix writes: `check_measured` and `check_mix`, beside each other.

The map: the lines in absolute planned order (`start_ms`, then `id`); `E` the latest planned end of the dialogue so
far, `P` its placed time. A line with no `E` or `start ≥ E` (right behind when equal, a made pause when after) goes
at `P + (start − E)` (the first at its planned start); one with `start < E` is a written overlap, placed at
`map(start)` on its own speaker's lane. Its placed end is its place + its kept speech + `TURN_MS`; a planned end after
`E` adds the breakpoint `(end, max(placed end, P))`, an overlap that overruns raises `P` (the last breakpoint
`(E, P)`). The breakpoints rise strictly in planned time and never fall in placed time: the map never runs back.
Cues, poses, panels and shots are mapped afterwards; the 1 s shot minimum moves a cut, never a clip.
"""
from __future__ import annotations

import bisect
import math
import re
from typing import Any

from hub.core.api import Invalid

from . import layout

KINDS = ("dialogue", "reaction", "effect", "music", "room")
DUCKED = ("reaction", "effect", "music")
LANE_GAIN, CLIP_GAIN = (-60.0, 24.0), (-60.0, 40.0)
REDO = "redo it (delete it from Sounds, then call script_track)"
ROOM = "room"
CLIP = ("take", "file", "at_ms", "in_ms", "out_ms", "gain_db", "fade_in_ms", "fade_out_ms", "loop")
MIX = ("lanes", "target", "length_ms", "note", "hash")


def interp(bp: list[tuple[int, int]], t: float) -> int:
    """The map at `t`: linear between the breakpoints around it, slope 1 before the first and after the last."""
    if not bp:
        return round(t)
    k = bisect.bisect_right([a for a, _ in bp], t)
    if k == 0:
        return round(t - bp[0][0] + bp[0][1])
    if k == len(bp):
        return round(t - bp[-1][0] + bp[-1][1])
    (a0, p0), (a1, p1) = bp[k - 1], bp[k]
    return round(p0 + (p1 - p0) * (t - a0) / (a1 - a0))


def kept(ident: str, take: dict, lengths: dict[str, int]) -> tuple[int, int]:
    """(in, out) of a take's kept span; refused when it has no measured sound (the room: kept whole instead)."""
    m = take.get("measured") or {}
    a, b = m.get("speech_start_ms"), m.get("speech_end_ms")
    if a is not None and b is not None and round(b) > round(a):
        return round(a), round(b)
    if ident == ROOM and lengths.get(ROOM, 0) > 0:
        return 0, int(lengths[ROOM])
    raise Invalid("mix", f"{ident}: its take {take['file']} has no measured sound: {REDO}")


def _rows(script: dict) -> tuple[list[dict], list[tuple[dict, dict]]]:
    shots = layout.shots(script)
    return shots, [(ev, shot) for shot in shots for ev in shot["events"]]


def place(script: dict, takes: dict, lengths: dict[str, int]) -> dict:
    """The placement -> {map, clips: {id: clip}, measured: {id: span}, shots: [span in script order], length_ms}; a clip
    is {id, kind ("line" or the cue's kind, or "room"), speaker, file, at_ms, in_ms, out_ms, gain_db, decay_ms}."""
    shots, rows = _rows(script)
    lines = sorted((ev for ev, _ in rows if ev["kind"] == "line"), key=lambda e: (e["start_ms"], e["id"]))
    bp: list[tuple[int, int]] = []
    big_e = big_p = None
    clips: dict[str, dict] = {}
    measured: dict[str, dict] = {}
    for ln in lines:
        a, b = kept(ln["id"], takes[ln["id"]], lengths)
        s, e = ln["start_ms"], ln["end_ms"]
        if big_e is None or s >= big_e:
            p = s if big_e is None else big_p + (s - big_e)
            if not bp or s > bp[-1][0]:
                bp.append((s, p))
        else:                                                       # a written overlap
            who = ln["speaker"].casefold()
            under = [o for o in lines if o is not ln and o["speaker"].casefold() == who
                     and o["start_ms"] < e and s < o["end_ms"]]
            if under:
                raise Invalid("mix", f"{ln['id']} overlaps {under[0]['id']}, a line of the same speaker "
                              f"({ln['speaker']}): move one with event_move")
            p = interp(bp, s)
        end = p + (b - a) + layout.TURN_MS
        if big_e is None or e > big_e:
            big_p = max(end, end if big_p is None else big_p)
            bp.append((e, big_p))
            big_e = e
        elif end > big_p:                                           # the overlap overruns: what follows pushed
            big_p = end
            bp[-1] = (big_e, big_p)
        clips[ln["id"]] = _clip(ln["id"], "line", takes[ln["id"]], a, b, p, ln["speaker"])
        measured[ln["id"]] = {"start_ms": p, "end_ms": p + b - a}
    for ev, _ in rows:
        if ev["kind"] == "cue" and ev["id"] in takes:
            a, b = kept(ev["id"], takes[ev["id"]], lengths)
            at = interp(bp, ev["start_ms"])
            clips[ev["id"]] = _clip(ev["id"], ev["cue"], takes[ev["id"]], a, b, at)
            measured[ev["id"]] = {"start_ms": at, "end_ms": at + b - a}
        elif ev["kind"] in ("pose", "cue"):                      # a cue left out mapped as a pose
            measured[ev["id"]] = {"start_ms": interp(bp, ev["start_ms"]), "end_ms": interp(bp, ev["end_ms"])}
    spans = _shots(shots, bp, max((c["at_ms"] + c["out_ms"] - c["in_ms"] for c in clips.values()), default=0))
    for ev, shot in rows:
        if ev["kind"] == "panel":
            span = spans[shots.index(shot)]
            measured[ev["id"]] = {"at_ms": min(max(interp(bp, ev["at_ms"]), span["start_ms"]), span["end_ms"] - 1)}
    length = spans[-1]["end_ms"] if spans else 0
    return {"map": bp, "clips": clips, "measured": measured, "shots": spans, "length_ms": length}


def apply(script: dict, placed: dict, mix: dict, renders: dict) -> dict:
    """The placement's write: `mix`, `renders` and every shot's and event's `measured` set in `script` (the planned
    times kept)."""
    script["mix"], script["renders"] = mix, renders
    for shot, span in zip(layout.shots(script), placed["shots"], strict=True):
        shot["measured"] = dict(span)
        for ev in shot["events"]:
            if ev["id"] in placed["measured"]:
                ev["measured"] = dict(placed["measured"][ev["id"]])
    return {"did": "mixed", "shot": None}


def _clip(ident: str, kind: str, take: dict, a: int, b: int, at: int, speaker: str | None = None) -> dict:
    m = take.get("measured") or {}
    gain = m.get("gain_db")
    return {"id": ident, "kind": kind, "speaker": speaker, "file": take["file"], "at_ms": at, "in_ms": a,
            "out_ms": b, "gain_db": 0.0 if gain is None else float(gain), "decay_ms": m.get("decay_ms")}


def room(takes: dict, lengths: dict[str, int]) -> dict:
    """The room's clip: its kept span (whole when it has no measured sound) at 0, looped by the mix."""
    a, b = kept(ROOM, takes[ROOM], lengths)
    return _clip(ROOM, ROOM, takes[ROOM], a, b, 0)


def fades(c: dict, length: int) -> tuple[int, int]:
    """For the mix's lanes: a clip's fades (in, out), each at most its sounding span: a line or effect 10 ms each;
    a reaction 100 in and out half its decay, at least 300; music 500 in, up to 1 s out; the room 500 each."""
    k = c["out_ms"] - c["in_ms"]
    if c["kind"] == "reaction":
        decay = c.get("decay_ms")
        return min(100, k // 2), min(1000, k // 2) if decay is None else min(max(300, int(decay) // 2), k // 2)
    if c["kind"] == "music":
        return min(500, k), min(1000, k // 2)
    return (min(500, length), min(500, length)) if c["kind"] == ROOM else (min(10, k), min(10, k))


def _shots(shots: list[dict], bp: list[tuple[int, int]], last_sound: int) -> list[dict]:
    """Each shot through the map, after the one before; at least `SHOT_MIN_MS`; the last to the last sound."""
    out: list[dict] = []
    for k, sh in enumerate(shots):
        start = interp(bp, sh["start_ms"])
        if out:
            start = max(start, out[-1]["end_ms"])
        end = max(interp(bp, sh["end_ms"]), start + layout.SHOT_MIN_MS)
        if k == len(shots) - 1:
            end = max(end, last_sound)
        out.append({"start_ms": start, "end_ms": end})
    return out


# ---------------------------------------------------------------- what the mix writes, checked on read
def _no(where: str, text: str) -> Invalid:
    return Invalid("script", f"{where}: {text}")


def _finite(value: Any, at: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise Invalid("script", f"{at} is not a finite number")
    items = value.items() if isinstance(value, dict) else enumerate(value) if isinstance(value, list) else ()
    for key, inner in items:
        _finite(inner, f"{at}.{key}")


def _whole(value: Any, lo: int = 0, hi: int | None = None) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and lo <= value and (hi is None or value <= hi)


def _num(value: Any, lo: float, hi: float) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and lo <= value <= hi


def _text(value: Any, hi: int) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= hi


def _keys(value: Any, need: tuple[str, ...], where: str, what: str) -> dict:
    if not isinstance(value, dict):
        raise _no(where, f"{what} is not an object")
    missing = [k for k in need if k not in value]
    if missing:
        raise _no(where, f"{what} has no {missing[0]}")
    extra = sorted(set(value) - set(need))
    if extra:
        raise _no(where, f"{what} has a key the format does not know: {extra[0]}")
    return value


def check_measured(value: Any, where: str, panel: bool) -> None:
    """`measured` of a shot or event: `{start_ms, end_ms}`, whole, of 0 or more, start ≤ end; a panel's `{at_ms}`."""
    _finite(value, f"{where}: measured")
    if panel:
        if not _whole(_keys(value, ("at_ms",), where, "measured")["at_ms"]):
            raise _no(where, "measured.at_ms is a whole millisecond of 0 or more")
        return
    _keys(value, ("start_ms", "end_ms"), where, "measured")
    if not (_whole(value["start_ms"]) and _whole(value["end_ms"]) and value["start_ms"] <= value["end_ms"]):
        raise _no(where, "measured is whole milliseconds, 0 ≤ start_ms ≤ end_ms")


def _clip_check(c: Any, where: str, ident: re.Pattern) -> None:
    _keys(c, CLIP, where, "a clip")
    if not (isinstance(c["take"], str) and (c["take"] == ROOM or ident.fullmatch(c["take"]))):
        raise _no(where, "take is an event id or room")
    if not _text(c["file"], 300):
        raise _no(where, "file is text of 1 to 300 characters")
    if not all(_whole(c[k]) for k in ("at_ms", "in_ms", "out_ms", "fade_in_ms", "fade_out_ms")) \
            or c["in_ms"] > c["out_ms"]:
        raise _no(where, "at_ms, in_ms, out_ms and the fades are whole milliseconds of 0 or more, in ≤ out")
    if not _num(c["gain_db"], *CLIP_GAIN):
        raise _no(where, f"gain_db is a number of {CLIP_GAIN[0]:g} to {CLIP_GAIN[1]:g}")
    if not isinstance(c["loop"], bool):
        raise _no(where, "loop is true or false")


def _lanes(lanes: Any, ident: re.Pattern) -> None:
    if not isinstance(lanes, list):
        raise _no("mix", "lanes is a list")
    names: set[str] = set()
    for n, lane in enumerate(lanes, 1):
        where = f"mix, lane {n}"
        _keys(lane, ("name", "kind", "gain_db", "duck", "clips"), where, "a lane")
        if not _text(lane["name"], 120) or lane["name"] in names:
            raise _no(where, "name is text of 1 to 120 characters, another lane's never")
        names.add(lane["name"])
        if lane["kind"] not in KINDS:
            raise _no(where, f"kind is one of {', '.join(KINDS)}")
        if not _num(lane["gain_db"], *LANE_GAIN):
            raise _no(where, f"gain_db is a number of {LANE_GAIN[0]:g} to {LANE_GAIN[1]:g}")
        if not isinstance(lane["duck"], bool):
            raise _no(where, "duck is true or false")
        if lane["duck"] and lane["kind"] not in DUCKED:
            raise _no(where, f"the {lane['kind']} lane is never ducked")
        if not isinstance(lane["clips"], list):
            raise _no(where, "clips is a list")
        for k, c in enumerate(lane["clips"], 1):
            _clip_check(c, f"{where}, clip {k}", ident)


def check_mix(mix: Any, renders: Any, ident: re.Pattern) -> None:
    """The `mix` and `renders` records (either None when absent)."""
    if mix is not None:
        _finite(mix, "mix")
        if not isinstance(mix, dict):                                       # the object first
            raise _no("mix", "the mix is not an object")
        _keys({k: v for k, v in mix.items() if k != "room_ms"}, MIX, "mix", "the mix")
        if "room_ms" in mix and not _whole(mix["room_ms"]):                 # optional
            raise _no("mix", "room_ms is a whole millisecond of 0 or more")
        _lanes(mix["lanes"], ident)
        target = _keys(mix["target"], ("lufs", "true_peak_dbtp", "source"), "mix", "the target")
        if not (_num(target["lufs"], -70, 0) and _num(target["true_peak_dbtp"], -20, 0)
                and _text(target["source"], 120)):
            raise _no("mix", "the target is lufs -70 to 0, true_peak_dbtp -20 to 0 and a source of 1 to 120 characters")
        if not _whole(mix["length_ms"]):
            raise _no("mix", "length_ms is a whole millisecond of 0 or more")
        if mix["note"] is not None and not _text(mix["note"], 600):          # four lines
            raise _no("mix", "note is null or text of 1 to 600 characters")
        if not _text(mix["hash"], 64):
            raise _no("mix", "hash is text of 1 to 64 characters")
    if renders is not None:
        _finite(renders, "renders")
        _keys(renders, ("track", "size", "stems"), "renders", "the renders")
        if not (renders["track"] is None or _text(renders["track"], 300)) or not (
                renders["size"] is None or _whole(renders["size"], 0, 2**63)):
            raise _no("renders", "track is null or text of 1 to 300 characters, size null or a whole number ≥ 0")
        if not isinstance(renders["stems"], dict):
            raise _no("renders", "stems is an object")
        for lane, stem in renders["stems"].items():
            _keys(stem, ("file", "size"), f"renders, stem {lane}", "a stem")
            if not (_text(stem["file"], 300) and _whole(stem["size"], 0, 2**63)):
                raise _no(f"renders, stem {lane}", "file is text of 1 to 300 characters, size a whole number ≥ 0")
