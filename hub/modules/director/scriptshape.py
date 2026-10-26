"""The script format (R48 §1): scenes → shots → events, every time a whole number of
milliseconds from the script's start. Version 1 is that alone; version 2 adds, before its scenes, the scene context
(`context.py`, R48 §8), and every scene's cast is a subset of the context's. A version-1 file reads with no
context, and is never rewritten. `read(value, characters)` gives the script back when every check holds, else one
`Invalid` line naming where ("Scene 1, shot 2, event l3: …"). Shape and references only: overlap, overrun and timing
are the Director's checks on arrival (Step 3) and timing's (Step 4), not a reason to refuse a file here. A version-2
script is written one call at a time: its scenes, a scene's shots and a shot's events may be empty, and a
shot may carry its `id` (`s` and a number, unique in the script). Version 2 also holds `panel` events:
`{id, kind, at_ms, picture, stale}`, an instant inside its shot, never read by the timing. A version-2
scene may hold `seconds`, the length named for it, a whole number from 1; and `done`, true only.
A shot's camera is text or blueprint §2's object (`camera.py`, version 2 only); a version-2 script
may hold `lock` {locked, at} and `takes` {event id: take} (`audioscript.check_takes`), read by the audio
script and written by Track. A version-2 shot may hold `seconds`, its held length (`layout.hold_ms`),
and `action`, what happens in it (`layout.action_ok`).
Version 2 may hold `mix` and `renders`, and `measured` on every shot and event (`place.check_mix`,
`place.check_measured`).
"""
from __future__ import annotations

import re
from collections.abc import Container
from typing import Any

from hub.core.api import Invalid

from . import audioscript, camera, layout, place
from . import context as scene_context

VERSIONS = (1, 2)
POSES = ("stand", "sit", "walk_step", "turn", "point", "arms_raised", "hand_to_face")   # R48 §4
CUES = ("effect", "music", "reaction")
KEYS = {"line": (("id", "kind", "start_ms", "end_ms", "speaker", "words"), ("language", "emotion", "pace")),
        "cue": (("id", "kind", "start_ms", "end_ms", "cue", "words"), ("anchor",)),
        "pose": (("id", "kind", "start_ms", "end_ms", "character", "pose"), ("anchor", "auto")),
        "panel": (("id", "kind", "at_ms", "picture", "stale"), ())}
SHOT = {1: (("start_ms", "end_ms", "events"), ("camera",)),
        2: (("start_ms", "end_ms", "events"), ("camera", "id", "measured", "seconds", "action"))}   # a shot's keys
SCENE = {1: (("title", "cast", "shots"), ()), 2: (("title", "cast", "shots"), ("seconds", "done"))}   # a scene's keys
TOP = {1: (("version", "scenes"), ()),
       2: (("version", "context", "scenes"), ("lock", "takes", "mix", "renders"))}   # the file's keys
ID = re.compile(r"[A-Za-z0-9_-]{1,24}")
SHOT_ID = re.compile(r"s[0-9]{1,6}")


def _may(keys: tuple[tuple[str, ...], tuple[str, ...]], version: int) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """An event's keys: version 2 may also hold `measured`."""
    return (keys[0], keys[1] + ("measured",)) if version == 2 else keys


def _no(where: str, text: str) -> Invalid:
    return Invalid("script", f"{where}: {text}" if where else text)


def _keys(value: Any, keys: tuple[tuple[str, ...], tuple[str, ...]], where: str, what: str) -> dict:
    """`value` when it is an object with every required key and no key but these."""
    need, may = keys
    if not isinstance(value, dict):
        raise _no(where, f"{what} is not an object")
    missing = [k for k in need if k not in value]
    if missing:
        raise _no(where, f"{what} has no {missing[0]}")
    extra = sorted(set(value) - set(need) - set(may))
    if extra:
        raise _no(where, f"{what} has a key the format does not know: {extra[0]}")
    return value


def _text(value: Any, where: str, what: str, hi: int | None = None) -> str:
    """Typed text: not blank, any length; `hi` only for the Hub's own values (a path, a time)."""
    if not isinstance(value, str) or not value.strip() or (hi is not None and len(value) > hi):
        raise _no(where, f"{what} is text of 1 to {hi} characters" if hi is not None else f"{what} is text, not blank")
    return value


def _whole(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _span(value: dict, where: str) -> tuple[int, int]:
    start, end = value["start_ms"], value["end_ms"]
    if not (_whole(start) and _whole(end) and 0 <= start < end):
        raise _no(where, "start_ms and end_ms are whole milliseconds, 0 ≤ start_ms < end_ms")
    return start, end


def _cast(value: Any, where: str, version: int) -> dict[str, str]:
    """The cast by its folded name -> the name as written, in its left-to-right order; a version-2
    scene's may be empty (a member removed, `frame._remove`), a version-1 scene's holds at least 1."""
    least = 1 if version == 1 else 0
    if not isinstance(value, list) or len(value) < least:
        raise _no(where, f"the cast is a list of {least} or more names")
    cast: dict[str, str] = {}
    for name in value:
        _text(name, where, "a cast name")
        if name.casefold() in cast:
            raise _no(where, f"{name} is in the cast twice")
        cast[name.casefold()] = name
    return cast


def _panel(ev: dict, shot: tuple[int, int], version: int, where: str) -> dict:
    """A sketch panel: version 2 only; an instant inside its shot; its picture's Temp id or null."""
    if version == 1:
        raise _no(where, "a panel is version 2")
    _keys(ev, _may(KEYS["panel"], version), where, "a panel")
    if not _whole(ev["at_ms"]) or not shot[0] <= ev["at_ms"] < shot[1]:
        raise _no(where, "at_ms is a whole millisecond at or after its shot's start and before its end")
    if ev["picture"] is not None:
        _text(ev["picture"], where, "picture", 300)
    if not isinstance(ev["stale"], bool):
        raise _no(where, "stale is true or false")
    return ev


def _event(ev: Any, shot: tuple[int, int], cast: dict[str, str], where: str, version: int = 2) -> dict:
    if not isinstance(ev, dict):
        raise _no(where, "an event is not an object")
    ident = ev.get("id")
    if not isinstance(ident, str) or not ID.fullmatch(ident):
        raise _no(where, "an event's id is 1 to 24 letters, digits, - or _")
    where = f"{where}, event {ident}"
    kind = ev.get("kind")
    if kind == "panel":
        return _panel(ev, shot, version, where)
    if not isinstance(kind, str) or kind not in KEYS:            # a list or object kind is a line
        raise _no(where, "kind is line, cue or pose")
    _keys(ev, _may(KEYS[kind], version), where, f"a {kind}")
    start, end = _span(ev, where)
    if start < shot[0] or end > shot[1]:
        raise _no(where, "the event is not inside its shot")
    if kind == "line":
        if not isinstance(ev["speaker"], str) or ev["speaker"].casefold() not in cast:
            raise _no(where, f"the speaker {ev['speaker']} is not in the scene's cast")
        _text(ev["words"], where, "words")
        for key in ("language", "emotion"):
            if key in ev:
                _text(ev[key], where, key)
        pace = ev.get("pace", 1)
        if isinstance(pace, bool) or not isinstance(pace, (int, float)) or not pace > 0:
            raise _no(where, "pace is words per second, more than 0")
    elif kind == "cue":
        if ev["cue"] not in CUES:
            raise _no(where, "a cue is effect, music or reaction")
        _text(ev["words"], where, "words")
    else:
        if not isinstance(ev["character"], str) or ev["character"].casefold() not in cast:
            raise _no(where, f"the character {ev['character']} is not in the scene's cast")
        if ev["pose"] not in POSES:
            raise _no(where, f"a pose is one of {', '.join(POSES)}")
        if "auto" in ev and (version == 1 or ev["auto"] is not True):   # a keyframe the Hub filled
            raise _no(where, "auto is version 2, and true")
    return ev


def _anchor(ev: dict, lines: dict[str, dict], where: str) -> None:
    """An anchor names a line of the same scene, and the event starts at that line's start or end."""
    anchor = _keys(ev["anchor"], (("line", "at"), ()), where, "an anchor")
    if anchor["at"] not in ("start", "end"):
        raise _no(where, "an anchor's at is start or end")
    line = lines.get(anchor["line"]) if isinstance(anchor["line"], str) else None
    if line is None:
        raise _no(where, f"the anchor names no line of this scene: {anchor['line']}")
    if ev["start_ms"] != line[f"{anchor['at']}_ms"]:
        raise _no(where, f"the event does not start at the {anchor['at']} of line {anchor['line']}")


def _lock(value: Any) -> None:
    """`{locked: true, at: <text>}` or `{locked: false, at: null}`."""
    _keys(value, (("locked", "at"), ()), "", "the lock")
    if not isinstance(value["locked"], bool):
        raise _no("", "the lock's locked is true or false")
    if value["locked"]:
        _text(value["at"], "", "the lock's at", 60)
    elif value["at"] is not None:
        raise _no("", "the lock's at is null when locked is false")


def renamed(value: Any) -> Any:
    """A version-2 file whose context is under another key, known by its shape (no `context`, exactly one key
    outside `TOP[2]`, that key's value an object holding `cast`), with that key named `context` in its place; anything
    else as given. Pure: the file is not written here; its next write saves what this gave."""
    if not isinstance(value, dict) or value.get("version") != 2 or "context" in value:
        return value
    unknown = [k for k in value if k not in TOP[2][0] + TOP[2][1]]
    if len(unknown) != 1 or not isinstance(value[unknown[0]], dict) or "cast" not in value[unknown[0]]:
        return value
    return {("context" if k == unknown[0] else k): v for k, v in value.items()}


def read(value: Any, characters: Container[str]) -> dict:
    """The script, every check held; else Invalid with one line naming where. `characters`: the
    folded names of the pictures in Characters (a version-2 context's cast must have one each)."""
    if not isinstance(value, dict):
        raise _no("", "The script is not an object")
    if "version" not in value:
        raise _no("", "The script has no version")
    version = value["version"]
    if not _whole(version) or version not in VERSIONS:
        raise _no("", "The script's version is 1 or 2")
    if version == 1 and "context" in value:
        raise _no("", "A version 1 script has no context; a context is version 2")
    _keys(value, TOP[version], "", "The script")
    held = scene_context.read(value["context"], characters) if version == 2 else None
    if "lock" in value:
        _lock(value["lock"])
    if "takes" in value:
        audioscript.check_takes(value["takes"], ID)
    place.check_mix(value.get("mix"), value.get("renders"), ID)
    scenes = value["scenes"]
    if not isinstance(scenes, list) or (version == 1 and not scenes):
        raise _no("", "The script has no scene")
    ids: set[str] = set()
    shot_ids: set[str] = set()
    last = 0
    for n, scene in enumerate(scenes, 1):
        where = f"Scene {n}"
        _keys(scene, SCENE[version], where, "the scene")
        _text(scene["title"], where, "the title")
        if "seconds" in scene and not (_whole(scene["seconds"]) and 1 <= scene["seconds"]):
            raise _no(where, "seconds is a whole number from 1")
        if "done" in scene and scene["done"] is not True:
            raise _no(where, "done is true")                   # absent until the scene is said done
        cast = _cast(scene["cast"], where, version)
        missing = [name for name in cast.values() if held is not None and name.casefold() not in held]
        if missing:
            raise _no(where, f"{missing[0]} is not in the context's cast")
        if not isinstance(scene["shots"], list) or (version == 1 and not scene["shots"]):
            raise _no(where, "the scene has no shot")
        lines: dict[str, dict] = {}
        anchored: list[tuple[dict, str]] = []
        for k, shot in enumerate(scene["shots"], 1):
            at = f"{where}, shot {k}"
            _keys(shot, SHOT[version], at, "the shot")
            if "id" in shot:
                if not isinstance(shot["id"], str) or not SHOT_ID.fullmatch(shot["id"]):
                    raise _no(at, "a shot's id is s and a number")
                if shot["id"] in shot_ids:
                    raise _no(at, "another shot has this id")
                shot_ids.add(shot["id"])
            span = _span(shot, at)
            if "seconds" in shot and not layout.held_seconds(shot["seconds"]):     # its held length
                raise _no(at, f"seconds is up to {layout.HOLD_MAX_S:g}, whole or tenths, more than 0")
            if "action" in shot and not layout.action_ok(shot["action"]):          # what happens in it
                raise _no(at, "action is text, not blank")
            if "measured" in shot:
                place.check_measured(shot["measured"], at, False)
            if span[0] < last:
                raise _no(at, "the shot starts before the shot before it ends")
            last = span[1]
            if "camera" in shot:
                why = camera.problem(shot["camera"], cast, version)
                if why is not None:
                    raise _no(at, why)
            if not isinstance(shot["events"], list):
                raise _no(at, "events is a list")
            for ev in shot["events"]:
                ev = _event(ev, span, cast, at, version)
                if ev["id"] in ids:
                    raise _no(f"{at}, event {ev['id']}", "another event has this id")
                ids.add(ev["id"])
                if "measured" in ev:
                    place.check_measured(ev["measured"], f"{at}, event {ev['id']}", ev["kind"] == "panel")
                if ev["kind"] == "line":
                    lines[ev["id"]] = ev
                if "anchor" in ev:
                    anchored.append((ev, f"{at}, event {ev['id']}"))
        for ev, at in anchored:
            _anchor(ev, lines, at)
    return value


def length_ms(script: dict) -> int:
    """The script's length: the end of its last shot; 0 with no shot."""
    return max((shot["end_ms"] for sc in script["scenes"] for shot in sc["shots"]), default=0)


def counts(script: dict) -> dict:
    """{scenes, shots, lines} of a script that reads."""
    shots = [s for sc in script["scenes"] for s in sc["shots"]]
    lines = sum(1 for s in shots for ev in s["events"] if ev["kind"] == "line")
    return {"scenes": len(script["scenes"]), "shots": len(shots), "lines": lines}
