"""What the script tools answer, pure: a write answers `{script, state}`, at most six lines (blueprint
A.3); `script_read` answers the whole script as compact lines, one per scene, shot and event, so a small model keeps
the ids it needs for its next call. Both name, on their first line, the cast with no picture in
Characters. A shot's camera is said as framing, move and who is in frame (`camera.said`); a locked script's
first line ends ` · locked`. A write's cast line ends with its scene's lines as `nth · speaker · first
words` (`refs.listing`), the number a `{speaker, nth}` ref sends; the read gives each scene's after its events.
The read lists each scene's gaps after its lines (`air.unfilled`); a shot line names the scene's dead air.
After a mix, a measured row's line ends with its span in the track, and a line after the head gives the track.
The read of a locked or complete script gives the takes line right after the head, before the track's.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from . import air, camera, clock, layout, length, refs, scriptshape
from .layout import secs

WRITE = "now write the story: scene_add, shot_add, line_add"   # `script_start`'s last line


def _span(item: dict) -> str:
    """A shot's own span, given once in script time (its offset start is always 0)."""
    return f"script {secs(item['start_ms'])}–{secs(item['end_ms'])} s"


def _head(name: str, script: dict, unpictured: Sequence[str]) -> str:
    """The first line; ` · Character 1 has no picture in Characters` (`Character 1, Character 2 have …`)
    at its end."""
    shots = layout.shots(script)
    head = f"{name} · {len(script['scenes'])} scenes · {len(shots)} shots · {secs(scriptshape.length_ms(script))} s"
    if unpictured:
        head += f" · {', '.join(unpictured)} {'has' if len(unpictured) == 1 else 'have'} no picture in Characters"
    return head


def _cast(script: dict, scene: int | None) -> str:
    if scene is not None:
        return f"scene {scene} cast: {', '.join(script['scenes'][scene - 1]['cast'])}"
    cast = script.get("context", {"cast": []})["cast"]
    return f"context cast: {', '.join(m['name'] for m in cast) or 'none yet'}"


def _ids(ids: list[str]) -> str:
    """Ids in order, a run of one kind's consecutive numbers as `l8–l9`."""
    runs: list[list[str]] = []
    for i in ids:
        last = runs[-1][-1] if runs else ""
        if last and last[0] == i[0] and last[1:].isdigit() and i[1:].isdigit() and int(i[1:]) == int(last[1:]) + 1:
            runs[-1].append(i)
        else:
            runs.append([i])
    return ", ".join(r[0] if len(r) == 1 else f"{r[0]}–{r[-1]}" for r in runs)


def _grouped(moved: dict[str, int], key: Any) -> list[tuple[int, list[str]]]:
    groups: dict[int, list[str]] = {}
    for i in sorted(moved, key=key):
        groups.setdefault(moved[i], []).append(i)
    return list(groups.items())


def _order(ident: str) -> tuple[int, int, str]:
    kind = "lcp".find(ident[:1])
    return (kind, int(ident[1:]) if ident[1:].isdigit() else 0, ident)


def moved(moves: dict | None) -> str | None:
    """`moved l8–l9, c4 +1.20 s; shots s4–s5 +1.20 s` when the timing moved events the call did not
    name; None when it moved none."""
    if not moves or not moves["events"]:
        return None
    parts = [f"{_ids(ids)} {by / 1000:+.2f} s" for by, ids in _grouped(moves["events"], _order)]
    shots = list(moves["shots"])
    parts += [f"shots {_ids(ids)} {by / 1000:+.2f} s" for by, ids in _grouped(moves["shots"], shots.index)]
    return "moved " + "; ".join(parts)


def _scene_of(script: dict, shot: dict) -> str:
    """` · scene 1 9.20 s of 15 s` when the shot's scene has a length named; ` · dead air 7.52 s` after it when
    the scene has dead air."""
    for n, sc in enumerate(script["scenes"], 1):
        if any(s.get("id") == shot.get("id") for s in sc["shots"]):
            silent = air.dead(sc) if "seconds" in sc else 0
            return length.shown(sc, n) + (f" · dead air {secs(silent)} s" if silent else "")
    return ""


def state(name: str, script: dict, done: dict, unpictured: Sequence[str] = ()) -> dict:
    """{script, state}: the script's scenes, shots and length; what was done; what the timing moved;
    the shot's span and room; the cast; the next step when given."""
    lines = [_head(name, script, unpictured), done["did"]]
    pushed = moved(done.get("moved"))
    if pushed is not None:
        lines.append(pushed)
    if done.get("keys"):
        lines.append(f"keys {_ids(done['keys'])} added")
    shot = done.get("shot")
    if shot is not None:
        room = shot["start_ms"] + layout.SHOT_MAX_MS - shot["end_ms"]
        lines.append(f"shot {shot['id']} · {_span(shot)} · {secs(room)} s left{_scene_of(script, shot)}")
    listed = refs.listing(script, done.get("scene") or len(script["scenes"]))
    lines.append(_cast(script, done.get("scene")) + (f" · lines: {listed}" if listed else ""))
    if done.get("next"):
        lines.append(done["next"])
    return {"script": name, "state": lines}


def tracked(item: dict) -> str:
    """` · track a–b s` for a measured shot or event, ` · track t s` for a measured panel, else ""."""
    m = item.get("measured")
    if m is None:
        return ""
    if "at_ms" in m:
        return f" · track {secs(m['at_ms'])} s"
    return f" · track {secs(m['start_ms'])}–{secs(m['end_ms'])} s"


def _track(track: dict) -> str:
    """`track: <state> · <why> · <file> · <length> s · <note>`, each part only when present."""
    parts = [track["state"], track.get("why"), track.get("file")]
    parts += [None if track.get("length_ms") is None else f"{secs(track['length_ms'])} s", track.get("note")]
    return "track: " + " · ".join(str(p) for p in parts if p)


def _event(ev: dict, shot: dict) -> str:
    span = clock.span(shot, ev["start_ms"], ev["end_ms"], short=True)
    if ev["kind"] == "line":
        extra = "".join(f" · {ev[k]}" for k in ("language", "emotion", "pace") if k in ev)
        return f'{ev["id"]} line {ev["speaker"]} {span} "{ev["words"]}"{extra}{tracked(ev)}'
    anchor = f" at {ev['anchor']['line']} {ev['anchor']['at']}" if "anchor" in ev else ""
    if ev["kind"] == "cue":
        return f'{ev["id"]} cue {ev["cue"]} {span} "{ev["words"]}"{anchor}{tracked(ev)}'
    return f"{ev['id']} pose {ev['character']} {ev['pose']} {span}{anchor}{tracked(ev)}"


def read(name: str, script: dict, unpictured: Sequence[str] = (), track: dict | None = None,
         pace: float | None = None, takes: str | None = None) -> dict:
    """{script, read}: the context's cast, set and style a line each, then each scene, shot and event; the track's line
    after the head when `track` is given and the script is measured (a mix wrote it). `pace`: the Hub's, the gap
    calls tried at it. `takes`: the takes line (`takesline.py`), right after the head."""
    out = [_head(name, script, unpictured), *([takes] if takes else [])]
    if track is not None and any("measured" in shot for shot in layout.shots(script)):
        out.append(_track(track))
    context = script.get("context")
    if context is not None:
        out.append(_cast(script, None))
        stage = context.get("set")
        if stage is not None:
            out.append(f"set: {stage['name']}" + (f" — {stage['description']}" if "description" in stage else ""))
        if "style" in context:
            out.append(f"style: {context['style']}")
    for n, sc in enumerate(script["scenes"], 1):
        out.append(f"scene {n} · {sc['title']} · cast {', '.join(sc['cast'])}{length.asked(sc)}")
        for shot in sc["shots"]:
            said = camera.said(shot)
            cam = f" · {said}" if said else ""
            out.append(f"{shot.get('id', '?')} · scene {n} · {_span(shot)}{cam}{tracked(shot)}")
            out += [_event(ev, shot) for ev in sorted(shot["events"], key=lambda e: (e["start_ms"], e["id"]))]
        listed = refs.listing(script, n)
        if listed:
            out.append(f"scene {n} lines: {listed}")
        found = air.unfilled(script, n, pace)
        if found:
            out.append(f"scene {n} gaps: {' | '.join(found)}")
    return {"script": name, "read": out}
