"""The sequence file's shape (`sequences.py`), checked; and an item's facts on one time scale. Stdlib only.

Version 2: `{"version": 2, "revision": n, "tracks": [[…], […]]}`, exactly two tracks. An item is
`{"clip": id, "in", "out"}` (frames of the clip) or `{"sound": id, "in", "out"}` (milliseconds of the sound), key
order as written; an item of track 2 adds `"at"`, where it starts in the sequence, in milliseconds, and may add
`"level"` (0-2, a factor), `"fade_in"` / `"fade_out"` (whole milliseconds) and `"duck"` (true: pressed down under
track 1's sound); an absent key is the default (1, 0, 0, off). Version 1
(`{"version": 1, "revision", "video": [{"clip", "in", "out"}], "audio": []}`, Stage 11) reads as version 2: its
`video` is track 1 and track 2 is empty; it is written as version 2 on its next save.

A sound is counted at 1000 "frames" a second (its milliseconds), so an item's kept seconds are `(out - in) / fps`
for both kinds (`facts`).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hub.core.files import Files

VERSION = 2
KEYS = ("version", "revision", "tracks")
V1_KEYS = ("version", "revision", "video", "audio")
KINDS = ("clip", "sound")
MS = 1000.0                                   # a sound's "frames" a second: its milliseconds


def whole(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def kind_of(item: dict) -> str:
    """"clip" or "sound": the item's one id key."""
    return "clip" if "clip" in item else "sound"


EXTRA = ("level", "fade_in", "fade_out", "duck")      # track 2's optional keys
LEVEL_MAX = 2.0


def keys_of(kind: str, track: int) -> tuple[str, ...]:
    """The keys an item must have."""
    return (kind, "in", "out", "at") if track == 1 else (kind, "in", "out")


def extra_ok(it: dict) -> bool:
    """Whether the optional keys an item carries are well formed."""
    level, duck = it.get("level", 1), it.get("duck", False)
    if isinstance(level, bool) or not isinstance(level, (int, float)) or not 0 <= level <= LEVEL_MAX:
        return False
    if not all(whole(it.get(k, 0)) and it.get(k, 0) >= 0 for k in ("fade_in", "fade_out")):
        return False
    return isinstance(duck, bool)


def _item_ok(it: Any, track: int) -> bool:
    if not isinstance(it, dict):
        return False
    kinds = [k for k in KINDS if k in it]
    if len(kinds) != 1 or not isinstance(it[kinds[0]], str):
        return False
    must, extra = set(keys_of(kinds[0], track)), set(EXTRA if track == 1 else ())
    if not must <= set(it) <= must | extra or not extra_ok(it):
        return False
    if not (whole(it["in"]) and whole(it["out"]) and 0 <= it["in"] < it["out"]):
        return False
    return track == 0 or (whole(it["at"]) and it["at"] >= 0)


def read_shape(value: Any) -> list[list[dict]] | None:
    """The two tracks of a file's value (version 1 or 2), or None when its shape is not one of them."""
    if not isinstance(value, dict) or not whole(value.get("revision")) or value["revision"] < 0:
        return None
    if value.get("version") == 1 and set(value) == set(V1_KEYS):
        video, audio = value["video"], value["audio"]
        if isinstance(video, list) and audio == [] and all(
                isinstance(it, dict) and set(it) == {"clip", "in", "out"} and _item_ok(it, 0) for it in video):
            return [video, []]
        return None
    if value.get("version") != VERSION or set(value) != set(KEYS):
        return None
    tracks = value["tracks"]
    if not isinstance(tracks, list) or len(tracks) != 2 or not all(isinstance(t, list) for t in tracks):
        return None
    if not all(_item_ok(it, k) for k, track in enumerate(tracks) for it in track):
        return None
    return [list(tracks[0]), list(tracks[1])]


def value_of(revision: int, tracks: list[list[dict]]) -> dict:
    return {"version": VERSION, "revision": revision, "tracks": tracks}


def facts(files: Files, item: dict) -> dict | None:
    """{kind, id, fps, frames, seconds, w, h, audio} of an item's file on one time scale (a sound: milliseconds as
    frames, `fps` 1000, no picture, always sound), or None when it is gone."""
    kind = kind_of(item)
    if kind == "clip":
        f = files.clip_facts(item["clip"])
        if f is None:
            return None
        return {"kind": "clip", "id": item["clip"], "fps": f["fps"], "frames": f["frames"], "seconds": f["seconds"],
                "w": f["w"], "h": f["h"], "audio": bool(f["audio"])}
    s = files.sound_facts(item["sound"])
    if s is None:
        return None
    return {"kind": "sound", "id": item["sound"], "fps": MS, "frames": round(s["seconds"] * MS),
            "seconds": s["seconds"], "w": 0, "h": 0, "audio": True}


def kept(item: dict, f: dict) -> float:
    return (item["out"] - item["in"]) / f["fps"]


def length(t1: list[tuple[dict, dict]], t2: list[tuple[dict, dict]]) -> float:
    """The seconds a saved file has: track 1's, or, when track 1 is empty, up to the end of track 2's last item."""
    if t1:
        return sum(kept(it, f) for it, f in t1)
    return max((it["at"] / MS + kept(it, f) for it, f in t2), default=0.0)
