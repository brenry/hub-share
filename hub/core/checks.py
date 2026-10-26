"""Plain-value checks a module's screen and job builder share: a whole number, a number, a seed, a run of seeds.

Pure and stdlib only; modules reach them through `hub.core.api` (`whole`, `number`, `seed_value`, `seeds`,
`plain_name`), which re-exports them. A bool is never a number here. Each refusal is one `Invalid` line naming the
field.
"""
from __future__ import annotations

import secrets
from typing import Any


def invalid(field: str, text: str) -> Exception:
    from hub.core.api import Invalid  # api.py re-exports this file: imported when first used

    return Invalid(field, text)


def plain_name(value: Any, field: str, what: str, room: int = 0) -> str:
    """A file's name as typed, trimmed (`drive.name_ok`: one segment, not hidden, `room` bytes left for its
    type and a temp file's parts), else Invalid "Use a plain <what> name, without slashes"."""
    from hub.core import drive  # drive imports api, which re-exports this file: imported when first used
    from hub.core.api import Invalid

    try:
        return drive.name_ok(value, room)
    except Invalid:
        raise invalid(field, f"Use a plain {what} name, without slashes") from None


def whole(value: Any, field: str, lo: int, hi: int, text: str | None = None) -> int:
    """`value` when it is a whole number from lo to hi, else Invalid (by default "<field> must be a whole number
    from <lo> to <hi>")."""
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise invalid(field, text or f"{field} must be a whole number from {lo} to {hi}")
    return value


def number(value: Any, field: str, lo: float, hi: float, text: str | None = None) -> float:
    """`value` as a float when it is a number from lo to hi, else Invalid (by default "<field> must be a number from
    <lo> to <hi>")."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not lo <= value <= hi:
        raise invalid(field, text or f"{field} must be a number from {lo} to {hi}")
    return float(value)


def seed_value(value: Any, hi: int) -> int | None:
    """None for "random"; else a whole number 0..hi, given as a number or as digit text (the tool server sends
    text)."""
    if value == "random":
        return None
    if isinstance(value, str) and value.isascii() and value.isdigit():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= hi:
        raise invalid("seed", f"seed must be random or a whole number from 0 to {hi}")
    return value


def seeds(first: int | None, count: int, hi: int) -> list[int]:
    """`count` seeds: random draws 0..hi when `first` is None, else first, first + 1, ... wrapped past hi to 0."""
    if first is None:
        return [secrets.randbelow(hi + 1) for _ in range(count)]
    return [(first + k) % (hi + 1) for k in range(count)]
