"""R54 prototype: the script-wide placement map of the mix (blueprint §12.3, §12.4, §19.1).
Pure, stdlib only. `place(rows, takes, lanes_before=None)` -> the placement: the planned->placed map (breakpoints),
one clip per line and cue (+ the room), the lanes, the shots' placed times, `measured` for every row, the length.

Rules (each a test in test_place.py):
- Lines in absolute planned order across all shots (`(start_ms, id)`); shots are never read for sound.
- `E`, `P`: the latest planned end of the dialogue so far and its placed time. A line with start >= E (right behind
  when ==, a made pause when >) is placed at P + (start - E): the running offset keeps a made pause exactly; right
  behind means it starts at the previous clip's measured speech end + TURN_MS (the planned line length already holds
  the turn pause, layout.line_ms). A line with start < E is a written overlap: placed at map(start) on its speaker's
  own lane; it never adds a breakpoint that falls back (rising breakpoints only); its overrun raises P.
- A line's placed end = placed start + kept speech + TURN_MS; overrun or underrun moves every later event.
- Cues, poses, panels and shots are mapped afterwards through the map (linear between breakpoints, slope 1 outside).
- The 1 s shot minimum moves a shot's placed cut later, never a clip.
"""
from __future__ import annotations

import bisect
import math
from typing import Any

TURN_MS = 180                   # layout.TURN_MS
SHOT_MIN_MS = 1_000             # layout.SHOT_MIN_MS
MAX_MS = 3_600_000              # scriptshape.MAX_MS
MAX_CAST = 16                   # context.MAX_CAST (the union of scenes' casts)
BEDS = ("reaction", "effect", "music", "room")
MAX_LANES = MAX_CAST + len(BEDS)    # 20; a cap of 12 would refuse a 9th speaker
MAX_CLIPS_LANE = 400
MAX_CLIPS = 1_000               # one ffmpeg input, one open file, per clip
GAIN_DB = (-60.0, 24.0)         # a lane's gain
CLIP_GAIN_DB = (-60.0, 40.0)    # a clip's gain (takejudge writes up to +46.9 for a take at -69.9 LUFS)
FADES = {"line": (10, 10), "effect": (10, 10), "reaction": (100, None), "music": (500, 1000), "room": (500, 500)}
REACTION_FADE_MIN = 300         # a reaction fades over half its measured decay, at least this
DUCKED = {"reaction": True, "effect": True, "music": True, "room": False}   # blueprint §12.3 (room: see README)
NO_ROOM = "room: no room take (its sound model is missing); the mix is made without it"


class Refused(ValueError):
    """The one line a reader would refuse, said before anything is written."""


def _num(x: Any, where: str, whole: bool = True, lo: float = 0, hi: float = MAX_MS) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise Refused(f"{where}: not a finite number ({x!r})")
    if whole and x != int(x):
        raise Refused(f"{where}: not whole milliseconds ({x!r})")
    if not lo <= x <= hi:
        raise Refused(f"{where}: {x} outside {lo}..{hi}")
    return int(x) if whole else float(x)


def interp(bp: list[tuple[int, int]], t: float) -> int:
    """The map: linear between breakpoints (planned strictly rising, placed never falling), slope 1 outside."""
    if not bp:
        return round(t)
    keys = [a for a, _ in bp]
    k = bisect.bisect_right(keys, t)
    if k == 0:
        return round(t - bp[0][0] + bp[0][1])
    if k == len(bp):
        return round(t - bp[-1][0] + bp[-1][1])
    (a0, p0), (a1, p1) = bp[k - 1], bp[k]
    return round(p0 + (p1 - p0) * (t - a0) / (a1 - a0))


def _take(takes: dict, ident: str) -> tuple[dict, int, int]:
    """(take, in_ms, out_ms) of the event `ident`, its numbers checked."""
    take = takes.get(ident)
    if not isinstance(take, dict) or not take.get("file"):
        raise Refused(f"{ident} has no take: call script_track")
    m = take.get("measured")
    if not isinstance(m, dict) or m.get("speech_start_ms") is None or m.get("speech_end_ms") is None:
        raise Refused(f"{ident}: its take has no measured sound (silent?)")
    a = _num(m["speech_start_ms"], f"{ident}: speech_start_ms")
    b = _num(m["speech_end_ms"], f"{ident}: speech_end_ms")
    if b <= a:
        raise Refused(f"{ident}: its take's sound ends at or before it starts ({a}..{b} ms)")
    for key in ("gain_db", "decay_ms", "lufs", "true_peak_dbtp"):
        if m.get(key) is not None:
            _num(m[key], f"{ident}: {key}", whole=False, lo=-1e9, hi=1e9)
    if m.get("gain_db") is not None:
        _num(m["gain_db"], f"{ident}: gain_db", whole=False, lo=CLIP_GAIN_DB[0], hi=CLIP_GAIN_DB[1])
    return take, a, b


def _rows(rows: dict) -> tuple[list, list, list]:
    """(shots, events, cast) checked: ids unique, kinds known, times finite whole ms, start < end."""
    shots, events, seen = rows.get("shots") or [], rows.get("events") or [], set()
    for sh in shots:
        _num(sh["start_ms"], f"shot {sh['id']}: start_ms")
        if _num(sh["end_ms"], f"shot {sh['id']}: end_ms") <= sh["start_ms"]:
            raise Refused(f"shot {sh['id']}: ends at or before it starts")
    for ev in events:
        ident = ev.get("id")
        if not isinstance(ident, str) or ident in seen or ident == "room":
            raise Refused(f"event {ident!r}: the id is missing, repeated or reserved")
        seen.add(ident)
        kind = ev.get("kind")
        if kind == "panel":
            _num(ev["at_ms"], f"{ident}: at_ms")
            continue
        if kind not in ("line", "cue", "pose"):
            raise Refused(f"{ident}: kind {kind!r} is not line, cue, pose or panel")
        if kind == "cue" and ev.get("cue") not in ("reaction", "effect", "music"):
            raise Refused(f"{ident}: a cue is reaction, effect or music")
        if _num(ev["end_ms"], f"{ident}: end_ms") <= _num(ev["start_ms"], f"{ident}: start_ms"):
            raise Refused(f"{ident}: ends at or before it starts")
    cast = list(rows.get("cast") or [])
    for ev in sorted(events, key=lambda e: (e.get("start_ms", e.get("at_ms")), e["id"])):
        if ev["kind"] == "line" and ev["speaker"] not in cast:
            cast.append(ev["speaker"])
    return shots, events, cast


def place(rows: dict, takes: dict, lanes_before: dict | None = None) -> dict:
    shots, events, cast = _rows(rows)
    lines = sorted((e for e in events if e["kind"] == "line"), key=lambda e: (e["start_ms"], e["id"]))
    speakers = [c for c in cast if any(ln["speaker"] == c for ln in lines)]
    if len(speakers) > MAX_CAST:
        raise Refused(f"{len(speakers)} speakers: a mix holds at most {MAX_CAST} ({MAX_LANES} lanes)")
    bp: list[tuple[int, int]] = []
    big_e = big_p = None
    clips, measured = {}, {}
    for ln in lines:
        take, a, b = _take(takes, ln["id"])
        s, e, kept = ln["start_ms"], ln["end_ms"], b - a
        if big_e is None or s >= big_e:
            p = s if big_e is None else big_p + (s - big_e)
            if not bp or s > bp[-1][0]:
                bp.append((s, p))
        else:                                                      # a written overlap
            under = [o for o in lines if o is not ln and o["speaker"] == ln["speaker"]
                     and o["start_ms"] < e and s < o["end_ms"]]
            if under:
                raise Refused(f"{ln['id']} overlaps {under[0]['id']}, a line of the same speaker ({ln['speaker']})")
            p = interp(bp, s)
        end = p + kept + TURN_MS
        if big_e is None or e > big_e:
            big_p = max(end, big_p if big_p is not None else end)
            bp.append((e, big_p))
            big_e = e
        elif end > big_p:                                          # the overlap overruns: later events pushed
            big_p = end
            bp[-1] = (big_e, big_p)
        clips[ln["id"]] = _clip(ln["id"], "line", take, a, b, p)
        measured[ln["id"]] = {"start_ms": p, "end_ms": p + kept}
    for ev in events:
        if ev["kind"] == "cue":
            take, a, b = _take(takes, ev["id"])
            at = interp(bp, ev["start_ms"])
            clips[ev["id"]] = _clip(ev["id"], ev["cue"], take, a, b, at)
            measured[ev["id"]] = {"start_ms": at, "end_ms": at + b - a}
        elif ev["kind"] == "pose":
            measured[ev["id"]] = {"start_ms": interp(bp, ev["start_ms"]), "end_ms": interp(bp, ev["end_ms"])}
        elif ev["kind"] == "panel":
            measured[ev["id"]] = {"at_ms": interp(bp, ev["at_ms"])}
    placed_shots = _shots(shots, bp)
    length = max([s["end_ms"] for s in placed_shots] + [c["at_ms"] + c["out_ms"] - c["in_ms"] for c in clips.values()]
                 + [0])
    notes = []
    if "room" in takes and takes["room"] is not None:
        take, a, b = _take(takes, "room")
        clips["room"] = {**_clip("room", "room", take, a, b, 0), "loop": True, "until_ms": length}
    else:
        notes.append(NO_ROOM)
    lanes = _lanes(events, clips, speakers, lanes_before or {})
    _num(length, "the track's length")
    return {"map": bp, "clips": clips, "lanes": lanes, "shots": placed_shots, "measured": measured,
            "length_ms": length, "notes": notes}


def _clip(ident: str, kind: str, take: dict, a: int, b: int, at: int) -> dict:
    kept = b - a
    fin, fout = FADES[kind]
    if kind == "reaction":
        decay = (take.get("measured") or {}).get("decay_ms")
        fout = min(1000, kept // 2) if decay is None else min(max(REACTION_FADE_MIN, int(decay) // 2), kept // 2)
    elif kind == "music":
        fout = min(fout, kept // 2)
    fin, fout = min(fin, kept // 2), min(fout, kept)
    gain = (take.get("measured") or {}).get("gain_db")
    return {"id": ident, "kind": kind, "file": take["file"], "at_ms": _num(at, f"{ident}: placed at"),
            "in_ms": a, "out_ms": b, "gain_db": 0.0 if gain is None else float(gain),
            "fade_in_ms": fin, "fade_out_ms": fout, "loop": False}


def _shots(shots: list, bp: list) -> list[dict]:
    """Each shot's planned times through the map; then the 1 s minimum moves the cut later (picture only)."""
    out, prev_end = [], None
    for sh in sorted(shots, key=lambda s: (s["start_ms"], s["id"])):
        start = interp(bp, sh["start_ms"])
        if prev_end is not None:
            start = max(start, prev_end)
        end = max(interp(bp, sh["end_ms"]), start + SHOT_MIN_MS)
        out.append({"id": sh["id"], "start_ms": start, "end_ms": end})
        prev_end = end
    return out


def _lanes(events: list, clips: dict, speakers: list, before: dict) -> list[dict]:
    by_id = {e["id"]: e for e in events}
    order = [(s, "dialogue") for s in speakers] + [(k, k) for k in BEDS]
    lanes = []
    for name, kind in order:
        held = [c for c in clips.values() if (kind == "dialogue" and c["kind"] == "line"
                                              and by_id[c["id"]]["speaker"] == name)
                or (kind != "dialogue" and c["kind"] == kind)]
        if not held:
            continue
        if len(held) > MAX_CLIPS_LANE:
            raise Refused(f"lane {name}: {len(held)} clips, over {MAX_CLIPS_LANE}")
        kept = before.get(name) or {}
        gain = _num(kept.get("gain_db", 0.0), f"lane {name}: gain_db", whole=False, lo=GAIN_DB[0], hi=GAIN_DB[1])
        duck = bool(kept.get("duck", kind != "dialogue" and DUCKED[kind]))
        lanes.append({"name": name, "kind": kind, "gain_db": gain, "duck": duck,
                      "clips": sorted(held, key=lambda c: (c["at_ms"], c["id"]))})
    if len(lanes) > MAX_LANES:
        raise Refused(f"{len(lanes)} lanes, over {MAX_LANES}")
    total = sum(len(lane["clips"]) for lane in lanes)
    if total > MAX_CLIPS:
        raise Refused(f"{total} clips, over the {MAX_CLIPS} one mix holds (one open file each)")
    return lanes
