"""A mixed script read from its file, never through the director's code; only what the cut uses is
checked, each problem one line (`Invalid("script", …)`).

A script is `<scripts>/<Name>.json`. It renders when it is version 2, locked (`lock.locked is True`), its track
`renders.track` a file in Sounds of `renders.size`, every shot and line `measured` with whole `start_ms <= end_ms`, and
the shots end to end. One mix writes the track and the measured times together (`director/mix.py`), so a locked
script's pair is taken as consistent; its hash is not checked (that needs the director's placement). `listing` gives
every script whose `renders.track` is set; one that does not parse is listed with its line; one never mixed is not.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from hub.core.api import Ctx, Invalid, plain_name

from . import parts

ROOT = "scripts"
UNREAD = "does not read as a script"
CHANGING = "{} is being changed: render it when its new mix is done"
NO_TRACK = "{} has no mixed track: Track it on the Storyboard"
UNMEASURED = "{}'s shots are not measured: mix it again"
GAPPED = "shot {} does not start where shot {} ends: mix it again"
UNKNOWN = "No script called {}"
ROOM = 12      # bytes kept free: the longest name filed from it, the group "<Script> shots" (+6), "<Script>.json"
TOP = ("version", "context", "scenes", "lock", "takes", "mix", "renders")   # the version-2 top-level keys


def folder(ctx: Ctx) -> Path:
    return Path(ctx.files.roots[ROOT])


def name_of(value: Any) -> str:
    return plain_name(value, "name", "script", room=ROOM)


def _whole(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _measured(item: dict) -> bool:
    m = item.get("measured")
    return isinstance(m, dict) and _whole(m.get("start_ms")) and _whole(m.get("end_ms")) \
        and m["start_ms"] <= m["end_ms"]


def check(ctx: Ctx, name: str, script: Any) -> dict:
    """The script's facts for the cut, else its one line: {name, script, track (path), size, mtime_ns}."""
    no = lambda text: Invalid("script", text)  # noqa: E731
    try:
        if not isinstance(script, dict) or script.get("version") != 2:
            raise no(f"{name} {UNREAD}")
        if not isinstance(script.get("lock"), dict) or script["lock"].get("locked") is not True:
            raise no(CHANGING.format(name))
        renders = script.get("renders") if isinstance(script.get("renders"), dict) else {}
        track, size = renders.get("track"), renders.get("size")
        sounds = Path(ctx.files.roots["sounds"])
        path = sounds / str(track or "")
        inside = bool(track) and isinstance(track, str) and os.path.realpath(path).startswith(
            os.path.realpath(sounds) + os.sep)
        st = path.stat() if inside and path.is_file() else None
        if st is None or st.st_size != size:
            raise no(NO_TRACK.format(name))
        pairs = parts.shot_list(script)
        if not pairs:
            raise no(UNMEASURED.format(name))
        for _, shot in pairs:
            lines = [ev for ev in shot.get("events") or [] if isinstance(ev, dict) and ev.get("kind") == "line"]
            if not _measured(shot) or not all(_measured(ev) for ev in lines):
                raise no(UNMEASURED.format(name))
        for k in range(1, len(pairs)):
            if pairs[k][1]["measured"]["start_ms"] != pairs[k - 1][1]["measured"]["end_ms"]:
                raise no(GAPPED.format(parts.shot_id(pairs[k][1], k + 1), parts.shot_id(pairs[k - 1][1], k)))
    except (KeyError, TypeError, AttributeError):
        raise no(f"{name} {UNREAD}") from None
    return {"name": name, "script": script, "track": path, "size": st.st_size, "mtime_ns": st.st_mtime_ns}


def _renamed(value: Any) -> Any:
    """The rule of `director/scriptshape.renamed`: a version-2 file with no `context` and exactly one key
    outside `TOP`, that key an object holding `cast`, read with that key named `context` in its place; else as given."""
    if not isinstance(value, dict) or value.get("version") != 2 or "context" in value:
        return value
    unknown = [k for k in value if k not in TOP]
    if len(unknown) != 1 or not isinstance(value[unknown[0]], dict) or "cast" not in value[unknown[0]]:
        return value
    return {("context" if k == unknown[0] else k): v for k, v in value.items()}


def load(ctx: Ctx, name: str) -> Any:
    """The parsed file; `UNKNOWN` when there is none; None when it does not parse."""
    path = folder(ctx) / f"{name}.json"
    if not path.is_file():
        raise Invalid("name", UNKNOWN.format(name))
    try:
        return _renamed(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def read(ctx: Ctx, value: Any) -> dict:
    """The named script checked (`check`)."""
    name = name_of(value)
    return check(ctx, name, load(ctx, name))


def listing(ctx: Ctx) -> list[dict]:
    """Every mixed script by name: {name, seconds, shots, why}; `why` None when it renders as far as its file says."""
    out = []
    root = folder(ctx)
    for path in sorted(root.glob("*.json"), key=lambda p: p.stem.casefold()) if root.is_dir() else ():
        if path.name.startswith("."):
            continue
        try:
            script = _renamed(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            out.append({"name": path.stem, "seconds": None, "shots": None, "why": f"{path.stem} {UNREAD}"})
            continue
        renders = script.get("renders") if isinstance(script, dict) else None
        if not isinstance(renders, dict) or not renders.get("track"):
            continue
        out.append({"name": path.stem, **summary(script), "why": why(ctx, path.stem, script)})
    return out


def summary(script: dict) -> dict:
    """{seconds, shots}: the mix's length and the shot count, None where the file does not say."""
    length = (script.get("mix") or {}).get("length_ms") if isinstance(script.get("mix"), dict) else None
    try:
        shots = len(parts.shot_list(script))
    except (KeyError, TypeError, AttributeError):
        shots = None
    return {"seconds": round(length / 1000, 2) if _whole(length) else None, "shots": shots}


def why(ctx: Ctx, name: str, script: Any) -> str | None:
    try:
        check(ctx, name, script)
    except Invalid as e:
        return e.text
    return None
