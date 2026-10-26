"""Where a script's sketch panels are, pure. A panel (`{id: "f<n>", kind: "panel", at_ms, picture,
stale}`) stands at each shot's start and at each instant strictly inside a shot where some character of the scene's
cast starts a pose that differs from its pose in force just before it. A member's pose in force at t in a shot: its
latest pose event in that shot starting at or before t (just before t: strictly before); none there: its latest pose in
the scene's earlier shots; none: `stand`. A pose's category is its name. Each panel has a cause: its shot's start, or
the pose events that change category at its instant.

A tool write takes the panels out before it changes anything (`take`), so the edit, timing and keyframe functions never
see one, and puts back each one whose cause still exists, at its cause's new time (`put`); the drawing pass adds a
panel for each cause with none (`fill`) and sets not drawn each panel whose picture is gone from Media (`forget`).
Causes are found per shot object: a change keeps its shots' objects.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import edit, layout

STAND = "stand"


def _fold(name: str) -> str:
    return name.casefold()


def _poses(shot: dict) -> list[dict]:
    return sorted((ev for ev in shot["events"] if ev["kind"] == "pose"), key=lambda ev: (ev["start_ms"], ev["id"]))


def _latest(shot: dict) -> dict[str, str]:
    """{folded character -> its latest pose in the shot}."""
    return {_fold(ev["character"]): ev["pose"] for ev in _poses(shot)}


def carried(scene: dict, shot: dict) -> dict[str, str]:
    """{folded character -> its latest pose in the scene's shots before `shot`}."""
    held: dict[str, str] = {}
    for earlier in scene["shots"]:
        if earlier is shot:
            break
        held.update(_latest(earlier))
    return held


def in_force(scene: dict, shot: dict, character: str, t: int, strict: bool = False) -> str:
    """The character's pose in force at `t` in `shot` (`strict`: just before `t`)."""
    who = _fold(character)
    found = [ev["pose"] for ev in _poses(shot) if _fold(ev["character"]) == who and
             (ev["start_ms"] < t if strict else ev["start_ms"] <= t)]
    return found[-1] if found else carried(scene, shot).get(who, STAND)


def causes(script: dict) -> list[dict]:
    """[{scene, shot, at_ms, start: bool, poses: set of pose ids}] in script order: each shot's start, then each
    instant inside it where a pose changes category."""
    out: list[dict] = []
    for scene in script["scenes"]:
        for shot in scene["shots"]:
            out.append({"scene": scene, "shot": shot, "at_ms": shot["start_ms"], "start": True, "poses": set()})
            poses = _poses(shot)
            for t in sorted({ev["start_ms"] for ev in poses if shot["start_ms"] < ev["start_ms"] < shot["end_ms"]}):
                changed = {ev["id"] for ev in poses if ev["start_ms"] == t and
                           ev["pose"] != in_force(scene, shot, ev["character"], t, strict=True)}
                if changed:
                    out.append({"scene": scene, "shot": shot, "at_ms": t, "start": False, "poses": changed})
    return out


def panels(script: dict) -> list[tuple[int, dict, dict]]:
    """[(scene number, shot, panel)] in script order (shot by shot, by time)."""
    out = []
    for n, scene in enumerate(script["scenes"], 1):
        for shot in scene["shots"]:
            out += [(n, shot, ev) for ev in sorted((e for e in shot["events"] if e["kind"] == "panel"),
                                                   key=lambda e: (e["at_ms"], e["id"]))]
    return out


def strip(script: dict) -> list[tuple[dict, dict]]:
    """The panels taken out of every shot: [(its shot, the panel)]."""
    out = []
    for shot in layout.shots(script):
        out += [(shot, ev) for ev in shot["events"] if ev["kind"] == "panel"]
        shot["events"] = [ev for ev in shot["events"] if ev["kind"] != "panel"]
    return out


def take(script: dict) -> list[tuple[dict, dict]]:
    """The panels taken out, each with its cause on the script as it was; a panel with none is dropped."""
    taken = strip(script)
    found = causes(script)
    out = []
    for shot, panel in taken:
        cause = next((c for c in found if c["shot"] is shot and c["at_ms"] == panel["at_ms"]), None)
        if cause is not None:
            out.append((panel, cause))
    return out


def _now(cause: dict, found: list[dict]) -> dict | None:
    if cause["start"]:
        return next((c for c in found if c["start"] and c["shot"] is cause["shot"]), None)
    return next((c for c in found if c["poses"] & cause["poses"]), None)


def put(script: dict, taken: list[tuple[dict, dict]]) -> None:
    """Each panel whose cause still exists back in its cause's shot at its new time, its id, picture and stale
    kept; a cause that went, or that another panel already holds, drops it."""
    found = causes(script)
    held: set[int] = set()
    for panel, cause in taken:
        now = _now(cause, found)
        if now is None or id(now) in held:
            continue
        held.add(id(now))
        now["shot"]["events"].append({**panel, "at_ms": now["at_ms"]})


def missing(script: dict) -> list[dict]:
    """The causes no panel stands at (a panel in the cause's shot at its instant)."""
    at = {(id(shot), ev["at_ms"]) for _, shot, ev in panels(script)}
    return [c for c in causes(script) if (id(c["shot"]), c["at_ms"]) not in at]


def fill(script: dict, counters: dict) -> int:
    """A panel (`picture` null, `stale` false, the next `f` id) for each cause with none. -> how many."""
    gone = missing(script)
    for cause in gone:
        cause["shot"]["events"].append({"id": edit.next_id(script, counters, "f"), "kind": "panel",
                                        "at_ms": cause["at_ms"], "picture": None, "stale": False})
    return len(gone)


def forget(script: dict, exists: Callable[[str], bool]) -> list[str]:
    """`picture` null on each panel whose picture `exists` refuses (gone from Media), and
    `stale` false: not drawn. -> their ids."""
    out = []
    for _, _, panel in panels(script):
        if panel["picture"] is not None and not exists(panel["picture"]):
            panel.update(picture=None, stale=False)
            out.append(panel["id"])
    return out


def find(script: dict, ident: str) -> tuple[int, dict, dict] | None:
    """(scene number, shot, panel) of the panel with this id, else None."""
    return next(((n, shot, ev) for n, shot, ev in panels(script) if ev["id"] == ident), None)


def drawn(script: dict, ident: str, picture: str) -> dict[str, Any]:
    """The panel's `picture` written; an answer for `scripts.change`."""
    found = find(script, ident)
    if found is not None:
        found[2]["picture"] = picture
    return {"written": found is not None}
