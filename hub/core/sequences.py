"""Sequences: one small JSON file per sequence, `<data>/clips/sequences/<name>.json`, beside the clips' day folders.

A file holds two tracks of item ids, their order, their in and out points and (track 2) where each starts, in the
shape `seqshape.py` checks: `{"version": 2, "revision": n, "tracks": [[…], […]]}`. Track 1 plays
back to back and holds clips or sounds, not both; track 2 holds items placed at `at` milliseconds. A clip's `in` and
`out` are frames, a sound's milliseconds; `out` is exclusive, and a save may leave it out (or null) for the whole
item, which the file then holds as the frame count or the length. A Stage 11 file (version 1) reads as track 1 and
is written as version 2 on its next save. `revision` rises by one on every write, and a save names the revision it
was drawn from (compare-and-swap). The name is the file's stem (`drive.name_ok`), and its temp file's name fits the
disk's 255 bytes.

An item is gone when its id is not a clip's or a sound's (`Files.kind`), its file is missing, or it no longer reads:
a read drops it and writes the file again; the listing only skips it. Nothing here moves, copies or erases a clip or
a sound. Written with `store.write_json` (temp file, fsync, `os.replace`); a torn temp file is erased at start
(`files.forget_older_records`). One lock around every read-modify-write.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hub.core import seqshape, temp
from hub.core.api import Invalid
from hub.core.seqshape import kind_of, whole
from hub.core.store import read_json, write_json

if TYPE_CHECKING:
    from hub.core.files import Files

FOLDER = "sequences"
ONLY = ("A sequence holds item ids, order, in and out points, where track 2's items start and their level, fades "
        "and duck only")
ROOM = len(".") + len(".json") + len(".12345678.tmp")   # the store's temp file `.<name>.json.<8 random>.tmp`
_lock = threading.Lock()


def name_of(name: Any) -> str:
    if not isinstance(name, str) or not name.strip():
        raise Invalid("name", "Name the sequence")
    return temp._plain(name, "name", "sequence", room=ROOM)


def _folder(files: Files) -> Path:
    return files.roots[temp.CLIPS] / FOLDER


def _path(files: Files, name: str) -> Path:
    return _folder(files) / f"{name}.json"


def _read(files: Files, name: str) -> tuple[int, list[list[dict]]]:
    """The file's revision and two tracks; a missing or unreadable file is refused."""
    try:
        value = read_json(_path(files, name))
    except (ValueError, OSError):
        value = False
    if value is None:
        raise Invalid("name", f"There is no sequence named {name}")
    tracks = seqshape.read_shape(value)
    if tracks is None:
        raise Invalid("name", f"The sequence {name} cannot be read")
    return value["revision"], tracks


def _write(files: Files, name: str, revision: int, tracks: list[list[dict]]) -> None:
    write_json(_path(files, name), seqshape.value_of(revision, tracks))


def _kept(files: Files, track: list) -> list[tuple[dict, dict]]:
    """The items whose file is not gone, each with its facts (`seqshape.facts`)."""
    return [(it, f) for it in track if (f := seqshape.facts(files, it)) is not None]


def listing(files: Files) -> list[dict]:
    """[{name, clips, seconds, changed}] by name: `clips` counts the items of both tracks, `seconds` is the length a
    saved file would have, `changed` the file's time; gone items are skipped and nothing is written. A file that does
    not read is listed empty, so it can still be deleted."""
    folder = _folder(files)
    if not folder.is_dir():
        return []
    names = [p.stem for p in folder.iterdir() if p.suffix == ".json" and not p.name.startswith(".") and p.is_file()]
    out = []
    for name in sorted(names, key=lambda n: (n.casefold(), n)):
        try:
            t1, t2 = (_kept(files, t) for t in _read(files, name)[1])
            changed = _path(files, name).stat().st_mtime
        except (Invalid, OSError):
            t1, t2, changed = [], [], 0.0
        out.append({"name": name, "clips": len(t1) + len(t2), "seconds": round(seqshape.length(t1, t2), 2),
                    "changed": changed})
    return out


def one(files: Files, name: Any) -> dict:
    """{name, revision, tracks, dropped}: gone items are dropped and the file written again (revision + 1)."""
    name = name_of(name)
    with _lock:
        revision, tracks = _read(files, name)
        kept = [[it for it, _ in _kept(files, t)] for t in tracks]
        dropped = sum(len(t) for t in tracks) - sum(len(t) for t in kept)
        if dropped:
            revision += 1
            _write(files, name, revision, kept)
    return {"name": name, "revision": revision, "tracks": kept, "dropped": dropped}


def new(files: Files, name: Any) -> dict:
    name = name_of(name)
    with _lock:
        if _path(files, name).exists():
            raise Invalid("name", f"A sequence named {name} already exists")
        _write(files, name, 0, [[], []])
    return {"name": name, "revision": 0, "tracks": [[], []], "dropped": 0}


def _item(files: Files, it: Any, track: int) -> dict:
    """One item of a save, checked against its file; -> the item as the file holds it."""
    if not isinstance(it, dict):
        raise Invalid("tracks", ONLY)
    kinds = [k for k in seqshape.KINDS if k in it]
    if len(kinds) != 1:
        raise Invalid("tracks", "Only clips and sounds go in a sequence")
    kind = kinds[0]
    if set(it) - set(seqshape.keys_of(kind, track)) - set(seqshape.EXTRA if track == 1 else ()):
        raise Invalid("tracks", ONLY)
    ident = it[kind]
    if not isinstance(ident, str) or files.kind(ident) != kind:
        raise Invalid("tracks", "Only clips and sounds go in a sequence")
    f = seqshape.facts(files, {kind: ident})
    if f is None:
        raise Invalid("tracks", f"That {kind} is gone")
    start, end, frames = it.get("in"), it.get("out"), f["frames"]
    end = frames if end is None else end                  # no out: the whole item, written as its frames or length
    if not (whole(start) and whole(end) and 0 <= start <= frames and 0 <= end <= frames):
        raise Invalid("tracks", f"In and out are frames of the clip, from 0 to {frames}" if kind == "clip"
                      else f"In and out are milliseconds of the sound, from 0 to {frames}")
    if end <= start:
        raise Invalid("tracks", f"A {kind} keeps at least one {'frame' if kind == 'clip' else 'millisecond'}")
    out = {kind: ident, "in": start, "out": end}
    if track == 1:
        at = it.get("at", 0)
        if not whole(at) or at < 0:
            raise Invalid("tracks", ONLY)
        out["at"] = at
        if not seqshape.extra_ok(it):
            raise Invalid("tracks", f"Level is 0 to {seqshape.LEVEL_MAX:g}, fades are milliseconds, duck is on or off")
        if it.get("level", 1) != 1:                       # a default is not written
            out["level"] = it["level"]
        for key in ("fade_in", "fade_out"):
            if it.get(key, 0):
                out[key] = it[key]
        if it.get("duck") is True:
            out["duck"] = True
    return out


def save(files: Files, name: Any, tracks: Any, revision: Any, limit: int | None = None) -> dict:
    """Compare-and-swap: refused unless `revision` is the file's; every item is checked again before writing; a
    track over `limit` items refused only when a caller names one (the Sequence module names none)."""
    name = name_of(name)
    if not isinstance(tracks, list) or len(tracks) != 2 or not all(isinstance(t, list) for t in tracks):
        raise Invalid("tracks", "A sequence has two tracks")
    if limit is not None and any(len(t) > limit for t in tracks):
        raise Invalid("tracks", f"A track holds at most {limit} items")
    with _lock:
        if not whole(revision) or revision != _read(files, name)[0]:
            raise Invalid("revision", "The sequence changed in another window")
        items = [[_item(files, it, k) for it in t] for k, t in enumerate(tracks)]
        if len({kind_of(it) for it in items[0]}) > 1:
            raise Invalid("tracks", "Track 1 holds clips or sounds, not both")
        _write(files, name, revision + 1, items)
    return {"name": name, "revision": revision + 1, "tracks": items, "dropped": 0}


def rename(files: Files, name: Any, to: Any) -> dict:
    """-> {name, revision} of the moved file. The file is read before it moves, so one that cannot be read stays."""
    name, to = name_of(name), name_of(to)
    with _lock:
        revision = _read(files, name)[0]
        if to != name:
            if _path(files, to).exists():
                raise Invalid("to", f"A sequence named {to} already exists")
            os.replace(_path(files, name), _path(files, to))
    return {"name": to, "revision": revision}


def delete(files: Files, name: Any) -> None:
    """The sequence's file only; never a clip."""
    name = name_of(name)
    with _lock:
        if not _path(files, name).is_file():
            raise Invalid("name", f"There is no sequence named {name}")
        _path(files, name).unlink()


class SequenceFiles:
    """`Files`' sequence methods (its `api.Files` part), kept here beside what they call."""

    def sequences(self: Files) -> list[dict]:
        return listing(self)

    def sequence(self: Files, name: str) -> dict:
        return one(self, name)

    def sequence_new(self: Files, name: str) -> dict:
        return new(self, name)

    def sequence_save(self: Files, name: str, tracks: list, revision: int, limit: int | None = None) -> dict:
        return save(self, name, tracks, revision, limit)

    def sequence_rename(self: Files, name: str, to: str) -> dict:
        return rename(self, name, to)

    def sequence_delete(self: Files, name: str) -> None:
        delete(self, name)

    def item_facts(self: Files, item: dict) -> dict | None:
        return seqshape.facts(self, item)
