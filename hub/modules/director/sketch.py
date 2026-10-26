"""A sketch panel's picture prompt (blueprint A.6), pure, from the script
alone: the composition, not the costume, in the script's own words. In order, joined as `render._words` joins
(a full stop after a part with no closing mark, a space between): the shot's camera
(`camera.words`, left out when empty); the set's name then its elements, joined by ", " (each with its whitespace
closed up; an empty one left out); each one in frame, left to right by home (`_homes`), as `<name> <pose>`: the cast
name as written and the pose in force (`panels.in_force`) with `_` as a space. Never the context's style, the set's
description, a prop, a look, a costume, a line's words, a cue, an `ignore` or a reference picture; and nothing of the
Hub's: no style sentence, no place or gaze words, no name replaced, no quoted words removed (CLAUDE.md, "No ...
rewording").
Whole whenever the context has a set; else the reason the panel waits. In frame is the camera's `on` when
given, else the scene's cast (`camera.in_frame`; this is the one place to read it).
"""
from __future__ import annotations

from . import camera, panels
from .render import _words


def _homes(names: list[str], context: dict) -> dict[str, int]:
    """{folded name -> home}: the context's, else spread by cast order (left to right) for a member without one."""
    members = {m["name"].casefold(): m for m in context["cast"]}
    n = len(names)
    out = {}
    for i, name in enumerate(names):
        home = members.get(name.casefold(), {}).get("home")
        out[name.casefold()] = home if isinstance(home, int) else (50 if n == 1 else round(i * 100 / (n - 1)))
    return out


def _closed(text: object) -> str:
    return " ".join(str(text or "").split())


def prompt(script: dict, scene: dict, shot: dict, at_ms: int) -> tuple[str | None, str | None]:
    """(the prompt, None) when it is whole; else (None, the reason the panel waits)."""
    context = script.get("context") or {"cast": []}
    stage = context.get("set")
    if not stage:
        return None, "the context has no set"
    framed = camera.in_frame(scene, shot)
    homes = _homes(scene["cast"], context)
    where = [t for t in (_closed(stage.get("name")), *(_closed(x) for x in stage.get("elements") or [])) if t]
    parts = [_closed(camera.words(shot)), ", ".join(where)]
    for name in sorted(framed, key=lambda c: homes[c.casefold()]):
        parts.append(f"{_closed(name)} {panels.in_force(scene, shot, name, at_ms).replace('_', ' ')}")
    return _words(*parts), None
