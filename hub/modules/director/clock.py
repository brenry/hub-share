"""One meaning of a time in the script tools, pure: the file keeps every time absolute from the
script's start; every time a tool takes or gives is an offset from the start of a shot. `rel` turns a
file time into that offset, `span` is an answer line's `0.00–2.49 s (script 3.64–6.13 s)`, `hints` a refusal's hints
with each instant an offset and the shot it counts from named. Every refusal that names a time goes through `hints`.
"""
from __future__ import annotations

from typing import Any

from .layout import secs

# The hint keys that are instants (`after_ms` and `latest_start_ms` too); amounts
# and counts stay as they are.
INSTANTS = ("suggested_start_ms", "suggested_end_ms", "shot_max_end_ms", "start_ms", "end_ms", "after_ms",
            "latest_start_ms")


def rel(shot: dict, ms: int) -> int:
    """`ms` (from the script's start) as the offset from `shot`'s start."""
    return ms - shot["start_ms"]


def span(shot: dict, start: int, end: int, short: bool = False) -> str:
    """`0.00–2.49 s (script 3.64–6.13 s)`; `short` without the two " s" (`script_read`'s event lines)."""
    here, there = f"{secs(rel(shot, start))}–{secs(rel(shot, end))}", f"{secs(start)}–{secs(end)}"
    return f"{here} (script {there})" if short else f"{here} s (script {there} s)"


def hints(shot: dict, **given: Any) -> dict:
    """`{shot, …}`, each instant of `given` (a file time) as the offset from `shot`'s start."""
    return {"shot": shot["id"], **{k: rel(shot, v) if k in INSTANTS else v for k, v in given.items()}}
