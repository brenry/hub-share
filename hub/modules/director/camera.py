"""A shot's camera as blueprint §2's object , pure: `{framing, move?, on?}`,
`framing` and `move` text, not blank, any length, `on` who is in frame, any names of the shot's scene cast,
each once (an empty `on` is nobody in frame). A camera written as text reads as its `framing`;
`objects` turns every text camera of a version-2 script into its object on a tool's write (`landing.write`), so a file
the tools wrote holds one form; a version-1 file keeps its text and is never written. `words` is the camera as the
sketch prompt takes it (framing, then the move): the old text for a converted camera, so the conversion changes no
prompt. `said` is the camera as the answers say it (`close shot · slow push in · on Character 1`).
"""
from __future__ import annotations

import copy
from typing import Any

from . import context as scene_context
from . import layout
from .layout import refuse

KEYS = ("framing", "move", "on")
TEXT = "camera is text, not blank"             # the text form's message (no length)


def _text_ok(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def problem(value: Any, cast: dict[str, str], version: int) -> str | None:
    """Why `value` is not a camera of a shot whose scene cast is `cast` (folded -> as written); None when it is."""
    if isinstance(value, str):
        return None if _text_ok(value) else TEXT
    if not isinstance(value, dict):
        return f"camera is text, or an object of {', '.join(KEYS)}"
    if version == 1:
        return "a camera object is version 2"
    extra = sorted(set(value) - set(KEYS))
    if extra:
        return f"the camera has a key the format does not know: {extra[0]}"
    if "framing" in value and not _text_ok(value["framing"]):     # a framing is not required
        return "the camera's framing is text, not blank"
    if "move" in value and not _text_ok(value["move"]):
        return "the camera's move is text, not blank"
    if "on" in value:
        on = value["on"]
        if not isinstance(on, list):
            return "the camera's on is a list of names"
        seen: set[str] = set()
        for name in on:
            if not isinstance(name, str) or name.casefold() not in cast:
                return f"the camera's on names {name}, who is not in the scene's cast"
            if name.casefold() in seen:
                return f"{name} is in the camera's on twice"
            seen.add(name.casefold())
    return None


def of(shot: dict) -> dict:
    """The shot's camera as the object (a copy): `{}` with no camera, `{framing: text}` for a text camera."""
    camera = shot.get("camera")
    if camera is None:
        return {}
    return {"framing": camera} if isinstance(camera, str) else copy.deepcopy(camera)


def words(shot: dict) -> str:
    """The sketch prompt's camera part: `framing`, then `, <move>` when given; "" with no framing."""
    cam = of(shot)
    framing = cam.get("framing", "")
    return f"{framing}, {cam['move']}" if framing and "move" in cam else framing or cam.get("move", "")


def said(shot: dict) -> str:
    """The answer words: `close shot · slow push in · on Character 1` (`on nobody` for an empty list); "" with no
    camera."""
    cam = of(shot)
    parts = [cam[k] for k in ("framing", "move") if k in cam]
    if "on" in cam:
        parts.append(f"on {', '.join(cam['on'])}" if cam["on"] else "on nobody")
    return " · ".join(parts)


def objects(script: dict) -> None:
    """Every text camera of a version-2 script as `{framing: text}`."""
    if script.get("version") != 2:
        return
    for shot in layout.shots(script):
        if isinstance(shot.get("camera"), str):
            shot["camera"] = {"framing": shot["camera"]}


def in_frame(scene: dict, shot: dict) -> list[str]:
    """Who is in frame: the camera's `on` (as the scene's cast writes them) when given, else the scene's cast."""
    cam = of(shot)
    if "on" not in cam:
        return list(scene["cast"])
    cast = {n.casefold(): n for n in scene["cast"]}
    return [cast.get(n.casefold(), n) for n in cam["on"]]


def renamed(script: dict, old: str, to: str) -> list[tuple[dict, Any]]:
    """Each shot whose camera changes when `old` is `to`, with its new camera: in a
    text camera, `framing` and `move` each name as written (`context.mention`) or its first word alone when no other
    member claims it (`context.first_word`), and each `on` entry equal to `old` by casefold."""
    others = [m["name"] for m in script["context"]["cast"] if m["name"].casefold() != old.casefold()]
    word = scene_context.first_word(old, [*others, *(n.split()[0] for n in others)])
    swap = {old: to, **({word: to.split()[0]} if word is not None else {})}
    pattern = scene_context.mention(*swap)

    def sub(text: str) -> str:
        return pattern.sub(lambda m: swap[m.group(0)], text)
    out: list[tuple[dict, Any]] = []
    for shot in layout.shots(script):
        camera = shot.get("camera")
        if isinstance(camera, str):
            new: Any = sub(camera)
        elif isinstance(camera, dict):
            new = {**camera, **{k: sub(camera[k]) for k in ("framing", "move") if isinstance(camera.get(k), str)}}
            if isinstance(camera.get("on"), list):
                new["on"] = [to if isinstance(n, str) and n.casefold() == old.casefold() else n for n in camera["on"]]
        else:
            continue
        if new == camera:
            continue
        out.append((shot, new))
    return out


def remove(script: dict, folded: str) -> None:
    """The member out of every shot's `on`."""
    for shot in layout.shots(script):
        camera = shot.get("camera")
        if isinstance(camera, dict) and isinstance(camera.get("on"), list):
            camera["on"] = [n for n in camera["on"] if not (isinstance(n, str) and n.casefold() == folded)]


def merged(shot: dict, given: Any, cast: list[str], n: int) -> dict:
    """The camera `given` (text is `{framing: text}`) merged into the shot's: a key sent replaces that key, `on`
    the list; refused in the camera's own words (`fields` hint `["camera"]`) or, for `on`, the scene's cast as the
    hint."""
    text = isinstance(given, str)
    if text:
        given = {"framing": given}
    if not isinstance(given, dict):
        raise refuse(f"A shot's camera is text, or an object of {', '.join(KEYS)}",
                     "Send camera {framing, move, on}", fields=["camera"])
    new = {**of(shot), **given}
    folded = {c.casefold(): c for c in cast}
    why = problem(new, folded, 2)
    if why is not None and ("on names" in why or "on twice" in why):
        bad = next((x for x in new["on"] if not isinstance(x, str) or x.casefold() not in folded), None)
        problem_text = (f"{bad} is not in scene {n}'s cast" if bad is not None
                        else why[0].upper() + why[1:])
        raise refuse(problem_text, "Name only the scene's cast in on", valid_speakers=cast)
    if why is not None:
        said = f"A shot's {TEXT}" if text else why[0].upper() + why[1:]
        raise refuse(said, "Send camera {framing, move, on}", fields=["camera"])
    return new
