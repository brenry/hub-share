"""`hub engine ...`: the engine settings as the engine installer changes them (Stage 10; install/install-engine.sh).

`set` points the Hub at an engine: its folder, its Python and the compilers its kernels build with, each checked on disk
as the Settings screen checks them (`pathrules`), and (when given) its arguments. The model and LoRA folders are the
ones set on the Settings screen: `set` never changes them. The settings it replaced are handed back, for `restore`
(an install undone, or the old engine put back). `clear` leaves the Hub with no engine (the engine lane starts down).
Each refusal is one line.
"""
from __future__ import annotations

import copy
import os
from typing import Any

from hub import pathrules
from hub.settings import validate

NO_FILE = "Not a program"


def program(value: str, field: str) -> str:
    """A compiler: a full path to a file the Hub may run, or empty for none."""
    if not value:
        return ""
    path = pathrules.python(value, field)
    if not os.access(path, os.X_OK):
        raise pathrules.Refused(field, NO_FILE)
    return path


def before(s: dict[str, Any]) -> dict[str, Any]:
    """What `set` and `clear` change, for `restore`."""
    return {"engine": copy.deepcopy(s["engine"])}


def engine_set(s: dict[str, Any], *, root: str, python: str, cc: str = "", cxx: str = "",
               engine_args: list[str] | None = None) -> dict[str, Any]:
    """The settings with the engine changed (checked whole), or `pathrules.Refused`. `engine_args`: the engine's
    arguments in place of the saved ones (None: unchanged). Model and LoRA folders stay as they are."""
    new = copy.deepcopy(s)
    eng = new["engine"]
    if engine_args is not None:
        eng["args"] = engine_args
    eng["root"] = pathrules.engine_root(root, "engine.root")
    eng["python"] = pathrules.python(python, "engine.python")
    eng["cc"], eng["cxx"] = program(cc, "engine.cc"), program(cxx, "engine.cxx")
    return validate(new)


def restore(s: dict[str, Any], saved: dict[str, Any]) -> dict[str, Any]:
    """The settings with the engine section `before` handed back; the model folders as they are now."""
    new = copy.deepcopy(s)
    new["engine"] = {**copy.deepcopy(saved["engine"]), "model_folders": list(s["engine"]["model_folders"]),
                     "helper_folders": list(s["engine"].get("helper_folders", []))}
    return validate(new)


def clear(s: dict[str, Any]) -> dict[str, Any]:
    """No engine: its folder, Python and compilers empty (the model and LoRA folders stay)."""
    new = copy.deepcopy(s)
    new["engine"].update(root="", python="", cc="", cxx="")
    return validate(new)
