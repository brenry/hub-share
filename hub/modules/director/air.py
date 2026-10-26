"""Held time and dead air (R48 §2, §3; R49 §5.8), pure. Time in a shot is
held by its lines and cues (start to end) and by each Director's pose (no `auto`: from its start for
`layout.POSE_MIN_MS`, at most to the shot's end); an `auto` keyframe and a panel hold nothing. A hole is a stretch of a
shot held by nothing longer than `layout.TURN_MS` (a turn's own pause is inside every line); an empty shot (no line,
cue or Director's pose) is one hole. `kept` refuses the write that makes a hole longer than `DEAD_AIR_MS` or lengthens
one (an existing one matched by its shot and its length); `gaps` lists, one line each, an empty shot and a
hole longer than `DEAD_AIR_MS` with the call(s) that mend it; `told` is `scene_change`'s answer: the
length asked and the length run, the dead air (no range, no fix line). A shot that
holds its own length (`layout.hold_ms`) is never empty and holds every instant of its span: no hole, no dead air.
"""
from __future__ import annotations

from . import clock, layout, length
from .layout import refuse, secs

DEAD_AIR_MS = 1_500              # Step 13's rulebook (`params.dead_air_ms`) replaces it
RANK = {"line": 0, "cue": 1, "pose": 2}
FIX = "Write a line, a cue or a pose there, or move it closer"      # a hole's fix when no call closes it


def _director(ev: dict) -> bool:
    return ev.get("kind") in ("line", "cue") or (ev.get("kind") == "pose" and not ev.get("auto"))


def held(shot: dict) -> list[tuple[int, int, dict]]:
    """(start, end, event) of each line, cue and Director's pose, file times, by start."""
    out = []
    for ev in shot["events"]:
        if not _director(ev):
            continue
        end = ev["end_ms"] if ev["kind"] != "pose" else min(ev["start_ms"] + layout.POSE_MIN_MS, shot["end_ms"])
        out.append((ev["start_ms"], end, ev))
    return sorted(out, key=lambda h: (h[0], RANK[h[2]["kind"]], h[2]["id"]))


def bare(shot: dict) -> bool:
    """Nothing in it: no line, cue or Director's pose (a held shot too)."""
    return not any(_director(ev) for ev in shot["events"])


def empty(shot: dict) -> bool:
    return bare(shot) and not layout.hold_ms(shot)


def holes(shot: dict) -> list[dict]:
    """{shot, start, end, after} of each hole (file times), `after` the event starting at its end (None at the
    shot's end); an empty shot's whole span, `after` None; none in a held shot."""
    if layout.hold_ms(shot):
        return []
    if empty(shot):
        return [{"shot": shot, "start": shot["start_ms"], "end": shot["end_ms"], "after": None}]
    out, at, spans = [], shot["start_ms"], held(shot)
    for start, end, _ev in [*spans, (shot["end_ms"], shot["end_ms"], None)]:
        if start - at > layout.TURN_MS:
            after = next((h[2] for h in spans if h[0] == start), None)
            out.append({"shot": shot, "start": at, "end": start, "after": after})
        at = max(at, end)
    return out


def dead(scene: dict) -> int:
    """The sum of the scene's holes longer than `DEAD_AIR_MS`, ms; a shorter one adds nothing."""
    return sum(gap for shot in scene["shots"] for h in holes(shot) if (gap := h["end"] - h["start"]) > DEAD_AIR_MS)


def _who(ev: dict | None) -> str:
    if ev is None:
        return ""
    if ev["kind"] == "line":
        return f"{ev.get('speaker')}'s line"
    return f"the {ev.get('cue')} cue" if ev["kind"] == "cue" else f"{ev.get('character')}'s pose"


def _before(scene: dict, ms: int) -> str:
    """The last line or cue of the scene ending at or before `ms`, in any shot: `<Subject 1>'s`, `the music cue`."""
    found = [ev for shot in scene["shots"] for ev in shot["events"]
             if ev.get("kind") in ("line", "cue") and ev["end_ms"] <= ms]
    if not found:
        return "the scene's start"
    ev = max(found, key=lambda e: (e["end_ms"], e["start_ms"], e["id"]))
    return f"{ev.get('speaker')}'s" if ev["kind"] == "line" else f"the {ev.get('cue')} cue"


def _unpaired(shot: dict, old: list[int]) -> dict | None:
    """The shot's holes longer than `DEAD_AIR_MS`, longest first, each paired with the shortest unpaired
    length of `old` (the same shot's holes before the call) at least as long; -> the first unpaired by start, or
    None."""
    left, out = sorted(old), []
    for h in sorted((h for h in holes(shot) if h["end"] - h["start"] > DEAD_AIR_MS),
                    key=lambda h: (h["start"] - h["end"], h["start"])):
        match = next((k for k, g in enumerate(left) if g >= h["end"] - h["start"]), None)
        if match is None:
            out.append(h)
        else:
            del left[match]
    return min(out, key=lambda h: h["start"]) if out else None


def kept(before: dict, after: dict, acted: str | None) -> None:
    """In each shot of `after` but an empty one, a hole longer than `DEAD_AIR_MS` with no hole of that shot in
    `before` (not empty there) as long, paired by length, is refused with where to close it; the first such in shot
    order."""
    was: dict = {}
    for shot in layout.shots(before):
        if not empty(shot):
            was.setdefault(shot.get("id"), []).extend(h["end"] - h["start"] for h in holes(shot))
    for scene in after["scenes"]:
        for shot in scene["shots"]:
            if empty(shot) or (h := _unpaired(shot, was.get(shot.get("id"), []))) is None:
                continue
            gap, ev = h["end"] - h["start"], h["after"]
            what = _who(ev) or f"the end of shot {shot.get('id')}"
            other = {} if ev is None or ev["id"] == acted else {"id": ev["id"]}
            raise refuse(f"{what[:1].upper()}{what[1:]} would leave {gap / 1000:.1f} s of silence after "
                         f"{_before(scene, h['start'])}", FIX,
                         **clock.hints(shot, gap_ms=gap, after_ms=h["start"], **other))


def _closing(shot: dict, h: dict) -> list[tuple[str, int]]:
    """The moves (id, offset in the shot) that close hole `h` before event X and every pause after X in
    its shot, in the order each lands: the Director's poses after X to their closed-up starts, first to last; each
    line and cue after X that starts later than the end of the lines and cues before it, last first, to that end
    (right behind it: it then follows them); X to the hole's start. Closed up: each held span after X starts where
    the held time before it ends, or, when it overlaps that time now, overlapping it as much. A pose
    whose character speaks a line before it that the chain moves waits for that line: named right before the first
    of them the chain moves, at no earlier than their ends as they stand then."""
    spans = held(shot)
    x = next(k for k, sp in enumerate(spans) if sp[2] is h["after"])
    poses: list[tuple[dict, int]] = []
    paused: list[tuple[dict, int]] = []
    was_all = now_all = was_sound = now_sound = h["start"]
    for k, (start, end, ev) in enumerate(spans[x:]):
        pose = ev["kind"] == "pose"
        was_at, now_at = (was_all, now_all) if pose else (was_sound, now_sound)
        moved = now_at if start >= was_at else start + now_at - was_at
        if pose:
            poses.append((ev, moved))
        else:
            if k and start > was_sound:
                paused.append((ev, was_sound))
            was_sound, now_sound = max(was_sound, end), max(now_sound, moved + end - start)
        was_all, now_all = max(was_all, end), max(now_all, moved + end - start)
    chain = [*reversed(paused), (h["after"], h["start"])]
    out: list[tuple[str, int]] = []
    waiting: dict[int, list[tuple[str, int]]] = {}
    for ev, at in poses:
        own = [k for k, (line, _) in enumerate(chain) if line["kind"] == "line" and ev.get("character") ==
               line.get("speaker") and line["start_ms"] < ev["start_ms"]]
        if not own:
            out.append((ev["id"], clock.rel(shot, at)))
            continue
        at = max(at, *(chain[k][0]["end_ms"] for k in own))
        waiting.setdefault(min(own), []).append((ev["id"], clock.rel(shot, at)))
    for k, (ev, at) in enumerate(chain):
        out += [*waiting.get(k, []), (ev["id"], clock.rel(shot, at))]
    return out


def _lands(script: dict, calls: list[tuple[str, int]], pace: float | None) -> bool:
    """The calls run in turn on a copy of the file as a write runs them (`landing.attempts`); -> whether each
    landed. Checked against the script's own cast (a move changes no cast)."""
    from . import landing, refs  # here: landing imports this module

    sent = layout.PACE if pace is None else pace
    cast = {m["name"].casefold() for m in (script.get("context") or {}).get("cast", [])}
    attempt = landing.attempts(script, cast, {}, sent, lambda tool, args: (
        lambda s, c, chars: refs.TOOLS[tool](s, args, pace=sent)))
    return attempt([("event_move", {"id": i, "start_ms": at}) for i, at in calls])


def unfilled(script: dict, n: int, pace: float | None = None) -> list[str]:
    """Scene n's empty shots and holes longer than `DEAD_AIR_MS`, shot by shot, each with the call(s) that mend it,
    joined by `, then ` in the order they land (times offsets in the shot). The calls are tried first at the Hub's
    `pace` (None: the engine's); a chain with a refused call is not named, the hole named with `FIX`."""
    out = []
    for k, shot in enumerate(script["scenes"][n - 1]["shots"], 1):
        sid = shot.get("id")
        if empty(shot):
            out.append(f'{sid}: nothing in it, shot {k} of scene {n} (event_remove {{id: "{sid}"}}, or line_add into '
                       "it)")
            continue
        for h in holes(shot):
            gap = h["end"] - h["start"]
            if gap <= DEAD_AIR_MS:
                continue
            a, b = clock.rel(shot, h["start"]), clock.rel(shot, h["end"])
            where = f"{sid} at {secs(a)}–{secs(b)} s: {secs(gap)} s of silence"
            if h["after"] is None:
                out.append(f"{where} at its end (line_add or cue_add into it)")
                continue
            chain = _closing(shot, h)
            if _lands(script, chain, pace):
                calls = ", then ".join(f'event_move {{id: "{i}", start_ms: {at}}}' for i, at in chain)
            else:
                calls = FIX[:1].lower() + FIX[1:]
            out.append(f'{where} before {h["after"]["id"]} ({calls})')
    return out


def told(scene: dict, n: int, done: bool) -> tuple[str, str | None]:
    """`scene_change`'s did-line (`scene 1 · done · 30 s asked · runs 16.68 s · 13.32 s under · no dead air`);
    the length asked and the length run, the exact difference, never a range; its fix is always None."""
    now, air = length.length(scene), dead(scene)
    parts = [f"scene {n}", *(["done"] if done else [])]
    parts[-1] += length.asked(scene)
    parts.append(f"runs {secs(now)} s")
    if "seconds" in scene:
        target = scene["seconds"] * 1000
        parts.append(f"{secs(target - now)} s under" if now < target else f"{secs(now - target)} s over"
                     if now > target else "on it")
    parts.append(f"dead air {secs(air)} s" if air else "no dead air")
    return " · ".join(parts), None
