"""The scripts folder, `<data>/scripts`: one `<Name>.json` per script, the name its file's stem.

Characters is `{folded name -> picture id}` of the pictures in Characters, handed in by the routes:
`one` answers each member's picture for its card, and a member with none reads and is named in
`unpictured`.
A file that does not read is listed with its one-line problem and can still be opened (the line shows where the
timeline would be), renamed and deleted. The Hub writes no script of its own into the folder.
Written with `api.write_json` (temp file, fsync, `os.replace`); a torn temp file is erased at start (`roots.OWN`).
One lock around every change. The script tools write version-2 scripts through `create` and `change`
(read, change in memory, check with `scriptshape.read`, write); a refusal writes nothing.
No file breaks the list. A number too long to read, a `\\u` escape that is not a character and a name
that is not UTF-8 are each a file's one problem, every problem is cut to 300 characters, and no text that does not
encode as UTF-8 leaves `load`.
"""
from __future__ import annotations

import copy
import json
import os
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from hub.core.api import Invalid, plain_name, write_json

from . import edit, scriptshape

ROOT = "scripts"                                   # the Hub's own root of that name (`roots.SCRIPTS`)
MAX_BYTES = 1_048_576
ROOM = len(".") + len(".json") + len(".12345678.tmp")   # the store's temp file `.<name>.json.<8 random>.tmp`
CUT = 300                                          # the longest problem line
NOT_UTF8 = "The file's name is not UTF-8: rename it in the scripts folder"
_lock = threading.Lock()


def name_of(name: Any) -> str:
    if not isinstance(name, str) or not name.strip():
        raise Invalid("name", "Name the script")
    return plain_name(name, "name", "script", room=ROOM)


def _path(folder: Path, name: str) -> Path:
    return folder / f"{name}.json"


def _names(folder: Path) -> list[str]:
    if not folder.is_dir():
        return []
    names = [p.stem for p in folder.iterdir() if p.suffix == ".json" and not p.name.startswith(".") and p.is_file()]
    return sorted(names, key=lambda n: (n.casefold(), n))


def _cut(e: Invalid) -> Invalid:
    """A problem over 300 characters as its first 299 and `…`, its field kept."""
    return e if len(e.text) <= CUT else Invalid(e.field, e.text[:CUT - 1] + "…")


def shown(stem: str) -> str:
    """A file's stem as the list shows it: a point that is not UTF-8 (`surrogateescape`) as `\ufffd`."""
    return stem.encode("utf-8", "surrogateescape").decode("utf-8", "replace")


def _utf8(stem: str) -> bool:
    try:
        stem.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def load(path: Path, characters: Mapping[str, str]) -> dict:
    """The script in the file; else Invalid with the file's one problem, at most 300 characters."""
    try:
        return _load(path, characters)
    except Invalid as e:
        raise _cut(e) from None


def _load(path: Path, characters: Mapping[str, str]) -> dict:
    try:
        if path.stat().st_size > MAX_BYTES:
            raise Invalid("script", "The file is over 1 MB")
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise Invalid("name", f"There is no script named {path.stem}") from None
    except (OSError, UnicodeDecodeError):
        raise Invalid("script", "The file cannot be read as text") from None
    try:
        value = json.loads(text)
    except json.JSONDecodeError as e:
        raise Invalid("script", f"The file is not JSON (line {e.lineno})") from None
    except ValueError:                                         # the int limit
        raise Invalid("script", "The file holds a number too long to read") from None
    except RecursionError:
        raise Invalid("script", "The file is nested too deep to read") from None
    try:
        json.dumps(value, ensure_ascii=False).encode("utf-8")
    except UnicodeEncodeError:                                 # a lone surrogate
        raise Invalid("script", "The file holds a \\u escape that is not a character") from None
    except RecursionError:
        raise Invalid("script", "The file is nested too deep to read") from None
    return scriptshape.read(scriptshape.renamed(value), characters)


def _summary(folder: Path, name: str, characters: Mapping[str, str]) -> dict:
    path = _path(folder, name)
    try:
        changed = path.stat().st_mtime
    except OSError:
        changed = 0.0
    if not _utf8(name):                                        # not read
        return {"name": shown(name), "seconds": 0, "scenes": 0, "shots": 0, "lines": 0, "changed": changed,
                "problem": NOT_UTF8}
    try:
        script = load(path, characters)
    except Invalid as e:
        return {"name": name, "seconds": 0, "scenes": 0, "shots": 0, "lines": 0, "changed": changed,
                "problem": e.text}
    return {"name": name, "seconds": scriptshape.length_ms(script) / 1000, **scriptshape.counts(script),
            "changed": changed, "problem": None}


def listing(folder: Path, characters: Mapping[str, str]) -> list[dict]:
    """[{name, seconds, scenes, shots, lines, changed, problem}] by name; nothing is written."""
    return [_summary(folder, name, characters) for name in _names(folder)]


def one(folder: Path, name: Any, characters: Mapping[str, str]) -> dict:
    """{name, seconds, problem, script, pictures, unpictured}: the script, or None and its problem when the file does
    not read; `pictures` {cast name: picture id} for the context's cards ({} without a context); `unpictured` the cast
    names with no picture in Characters."""
    name = name_of(name)
    path = _path(folder, name)
    if not path.is_file():
        raise Invalid("name", f"There is no script named {name}")
    try:
        script = load(path, characters)
    except Invalid as e:
        return {"name": name, "seconds": 0, "problem": e.text, "script": None, "pictures": {}, "unpictured": []}
    cast = script.get("context", {"cast": []})["cast"]
    return {"name": name, "seconds": scriptshape.length_ms(script) / 1000, "problem": None, "script": script,
            "pictures": {m["name"]: characters[m["name"].casefold()] for m in cast
                         if m["name"].casefold() in characters},
            "unpictured": [m["name"] for m in cast if m["name"].casefold() not in characters]}


def rename(folder: Path, name: Any, to: Any) -> dict:
    """The file renamed, whether it reads or not. -> {name}."""
    name, to = name_of(name), name_of(to)
    with _lock:
        if not _path(folder, name).is_file():
            raise Invalid("name", f"There is no script named {name}")
        if to != name:
            if _path(folder, to).exists():
                raise Invalid("to", f"A script named {to} already exists")
            os.replace(_path(folder, name), _path(folder, to))
    return {"name": to}


def delete(folder: Path, name: Any) -> None:
    """The script's file, for good."""
    name = name_of(name)
    with _lock:
        if not _path(folder, name).is_file():
            raise Invalid("name", f"There is no script named {name}")
        _path(folder, name).unlink()


def names(folder: Path) -> list[str]:
    """The names as the list shows them."""
    return [shown(n) for n in _names(folder)]


def exists(folder: Path, name: str) -> bool:
    return _path(folder, name).is_file()


def create(folder: Path, name: str, script: dict, characters: Mapping[str, str]) -> None:
    """A new script's file; a name taken is refused."""
    with _lock:
        if _path(folder, name).exists():
            raise edit.refuse(f"A script named {name} already exists", "Use another name, or script_read with this "
                              "name to go on writing it")
        scriptshape.read(script, characters)
        write_json(_path(folder, name), script)


def readable(folder: Path, name: str, characters: Mapping[str, str]) -> dict:
    """The script in the file; else `No script is open` or the file's one problem as a refusal."""
    if not _path(folder, name).is_file():
        raise edit.refuse("No script is open", "Call script_start, or script_read with a name")
    try:
        return load(_path(folder, name), characters)
    except Invalid as e:
        raise edit.refuse(f"{name} does not read: {e.text}", "Mend the file as the line says, or start a new script "
                          "with script_start") from None


def opened(folder: Path, name: str, characters: Mapping[str, str]) -> dict:
    """The script a tool writes: a version-2 file that reads; else the refusal of a missing, unreadable or version-1
    file."""
    script = readable(folder, name, characters)
    if script["version"] == 1:
        raise edit.refuse(f"{name} is a version 1 script", "Start a new script with script_start")
    return script


def change(folder: Path, name: str, characters: Mapping[str, str], fn: Callable[[dict], dict]) -> tuple[dict, dict]:
    """One locked read-change-write: `fn` changes a copy of the script and answers what it did; the
    copy is checked as a file is and written. -> (the script written, `fn`'s answer). A refusal writes nothing."""
    with _lock:
        script = copy.deepcopy(opened(folder, name, characters))
        done = fn(script)
        try:
            scriptshape.read(script, characters)
        except Invalid as e:
            raise edit.refuse(e.text, "Send the call again with that changed") from None
        write_json(_path(folder, name), script)
    return script, done
