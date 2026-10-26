"""Folder and file paths a screen may set: checked, never created, never written.

Each check raises `Refused(field, text)` with one short line the Settings screen shows as is.
"""
from __future__ import annotations

import os
from typing import Any

MAX_FOLDERS = 32


class Refused(ValueError):
    def __init__(self, field: str, text: str) -> None:
        super().__init__(text)
        self.field, self.text = field, text


def _absolute(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Refused(field, "Enter a full path")
    if "\0" in value:
        raise Refused(field, "Not a valid path")
    if not os.path.isabs(value):
        raise Refused(field, "Use a full path, starting with /")
    return os.path.normpath(value)


def folder(value: Any, field: str, *, write: bool = False) -> str:
    path = _absolute(value, field)
    if not os.path.exists(path):
        raise Refused(field, "Folder not found")
    if not os.path.isdir(path):
        raise Refused(field, "Not a folder")
    if not os.access(path, os.R_OK | os.X_OK):
        raise Refused(field, "Not readable")
    if write and not os.access(path, os.W_OK | os.X_OK):
        raise Refused(field, "Not writable")
    return path


def folders(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_FOLDERS:
        raise Refused(field, f"Up to {MAX_FOLDERS} folders")
    out: list[str] = []
    for i, item in enumerate(value):
        path = folder(item, f"{field}[{i}]")
        if path in out:
            raise Refused(f"{field}[{i}]", "Already listed")
        out.append(path)
    return out


def engine_root(value: Any, field: str) -> str:
    path = folder(value, field)
    if not os.path.isfile(os.path.join(path, "wgp.py")):
        raise Refused(field, "No wgp.py in this folder")
    return path


def python(value: Any, field: str) -> str:
    path = _absolute(value, field)
    if not os.path.exists(path):
        raise Refused(field, "File not found")
    if not os.path.isfile(path) or not os.access(path, os.X_OK):
        raise Refused(field, "Not a Python")
    return path


def overlaps(a: str, b: str) -> bool:
    """One folder is the other or holds it (real paths)."""
    ra, rb = os.path.realpath(a), os.path.realpath(b)
    return os.path.commonpath([ra, rb]) in (ra, rb)


def drive_root(value: Any, field: str, s: dict, hub_own: list[str]) -> str:
    """The Drive: writable, apart from the Hub's own data folder (Temp lives there), outside the engine, model and
    LoRA folders."""
    path = folder(value, field, write=True)
    if any(overlaps(path, own) for own in hub_own):
        raise Refused(field, "That is the Hub's own folder; pick your own folder")
    eng = s["engine"]
    reads = [(eng["root"], "Inside the engine folder")]
    reads += [(f, "Inside a model folder") for f in (*eng["model_folders"], *eng.get("helper_folders", []))]
    reads += [(f, "Inside a LoRA folder") for f in s["modules"].get("loras", {}).get("folders", [])]
    for top, text in reads:
        if top and os.path.isabs(top) and overlaps(path, top):
            raise Refused(field, text)
    return path
