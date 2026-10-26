"""A mixed script's shots as parts on one frame grid, pure (no I/O).

`fps` is the model's (`Cut.facts`); `s0` the first shot's measured start, `E` the last's end; a time's frame is
`g(t) = round((t - s0) * fps / 1000)` and shot k is frames `[g(start_k), g(end_k))`, so the shots' frames sum to
`g(E)` with no drift and the join's cuts land on the track's times. A shot of more than one window (`W`) is split at
the middle of a gap between its lines (overlapping or touching lines merged first): from a part's start, the latest
such frame within `W`; none: a cut at `start + W`, said as `split: "window"` (the tab's `cut mid-line`). A part renders
`F` frames, the shortest lattice length (`min + k * step`) that holds it, never under `min`; the extra frames are
trimmed at the join.
"""
from __future__ import annotations

import math
from typing import Any


def grid(t: float, s0: float, fps: float) -> int:
    """A time's frame on the grid (half up)."""
    return math.floor((t - s0) * fps / 1000 + 0.5)


def render_frames(n: int, lo: int, step: int) -> int:
    """`F`: `min` when `n <= min`, else `min + ceil((n - min) / step) * step`."""
    return lo if n <= lo else lo + -(-(n - lo) // step) * step


def shot_list(script: dict) -> list[tuple[dict, dict]]:
    """Every (scene, shot) in script order."""
    return [(scene, shot) for scene in script["scenes"] for shot in scene["shots"]]


def shot_id(shot: dict, k: int) -> str:
    """A shot's `id`, else its 1-based number."""
    ident = shot.get("id")
    return str(ident) if isinstance(ident, str) and ident else str(k)


def camera(shot: dict) -> dict:
    """The shot's camera as an object: `{}` with none, `{framing: text}` for a text camera (as the director's
    `camera.of`, read here, never imported)."""
    cam = shot.get("camera")
    if cam is None:
        return {}
    return {"framing": cam} if isinstance(cam, str) else dict(cam)


def in_frame(scene: dict, shot: dict) -> list[str]:
    """Who is in frame: the camera's `on` (as the scene's cast writes them) when given, else the scene's cast."""
    cam = camera(shot)
    cast = list(scene.get("cast") or [])
    if "on" not in cam:
        return cast
    named = {str(n).casefold(): n for n in cast}
    return [named.get(str(n).casefold(), n) for n in cam["on"]]


def lines_of(shot: dict) -> list[dict]:
    """The shot's lines by their measured start."""
    found = [ev for ev in shot.get("events") or [] if ev.get("kind") == "line"]
    return sorted(found, key=lambda ev: (ev["measured"]["start_ms"], str(ev.get("id"))))


def candidates(shot: dict, s0: float, fps: float, lo: int, hi: int) -> list[int]:
    """The frames strictly inside `(lo, hi)` at the middle of each gap between the shot's merged line spans."""
    spans: list[list[float]] = []
    for ev in lines_of(shot):
        a, b = ev["measured"]["start_ms"], ev["measured"]["end_ms"]
        if spans and a <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], b)
        else:
            spans.append([a, b])
    cuts = (grid((left[1] + right[0]) / 2, s0, fps) for left, right in zip(spans, spans[1:], strict=False))
    return sorted({c for c in cuts if lo < c < hi})


def cuts(f_start: int, f_end: int, inside: list[int], window: int) -> list[tuple[int, int, str | None]]:
    """The shot `[f_start, f_end)` as parts `(f0, n, split)`, each at most `window` frames."""
    out, at = [], f_start
    while f_end - at > window:
        fit = [c for c in inside if at < c <= at + window]
        end, how = (fit[-1], "line") if fit else (at + window, "window")
        out.append((at, end - at, how))
        at = end
    out.append((at, f_end - at, None))
    return out


def _secs(x: float) -> float:
    return round(x, 2)


def part_lines(shot: dict, who: list[str], start_ms: float, end_ms: float, seconds: float) -> list[dict]:
    """The shot's lines overlapping the part, relative to its start, clipped to `[0, seconds]`."""
    framed = {str(n).casefold() for n in who}
    out = []
    for ev in lines_of(shot):
        a, b = ev["measured"]["start_ms"], ev["measured"]["end_ms"]
        if not (a < end_ms and (b > start_ms or a >= start_ms)):
            continue
        rel_a, rel_b = (a - start_ms) / 1000, (b - start_ms) / 1000
        out.append({"speaker": str(ev.get("speaker") or ""), "words": str(ev.get("words") or ""),
                    "from_s": _secs(min(max(rel_a, 0.0), seconds)), "to_s": _secs(min(max(rel_b, 0.0), seconds)),
                    "in_frame": str(ev.get("speaker") or "").casefold() in framed})
    return out


def split(script: dict, facts: dict[str, Any]) -> list[dict]:
    """Every part of the script, in order."""
    fps, lo, step, window = float(facts["fps"]), int(facts["min"]), max(1, int(facts["step"])), int(facts["window"])
    pairs = shot_list(script)
    s0 = pairs[0][1]["measured"]["start_ms"]
    out: list[dict] = []
    for k, (scene, shot) in enumerate(pairs, 1):
        sid, who, cam = shot_id(shot, k), in_frame(scene, shot), camera(shot)
        f_start, f_end = grid(shot["measured"]["start_ms"], s0, fps), grid(shot["measured"]["end_ms"], s0, fps)
        inside = candidates(shot, s0, fps, f_start, f_end)
        pieces = cuts(f_start, f_end, inside, window)
        for j, (f0, n, how) in enumerate(pieces, 1):
            start_ms, end_ms = s0 + f0 * 1000 / fps, s0 + (f0 + n) * 1000 / fps
            out.append({"id": sid if len(pieces) == 1 else f"{sid}.{j}", "shot": sid, "part": j, "of": len(pieces),
                        "f0": f0, "n": n, "start_ms": start_ms, "end_ms": end_ms,
                        "render": render_frames(n, lo, step), "who": list(who),
                        "lines": part_lines(shot, who, start_ms, end_ms, n / fps),
                        "camera": {k2: cam[k2] for k2 in ("framing", "move") if isinstance(cam.get(k2), str)},
                        "split": how})
    return out


def span(script: dict) -> tuple[float, float]:
    """(s0, E): the first shot's measured start and the last's end."""
    pairs = shot_list(script)
    return pairs[0][1]["measured"]["start_ms"], pairs[-1][1]["measured"]["end_ms"]
