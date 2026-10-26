"""The seam's types (`engineapi`) as plain JSON values and back, both ways checked. Stdlib only.

`wire(value)` turns a dataclass (nested) into dicts and lists; `parse(cls, data)` turns them back, refusing an unknown
or missing field and a value of the wrong type. A field whose wire name is not a Python name says so in its metadata
(`{"wire": "in"}`). A request crosses as its fields plus `kind` (`request_wire`, `request_parse`).
"""
from __future__ import annotations

import dataclasses
import types
import typing
from typing import Any

try:
    from .engineapi import KIND_ROLES, REQUESTS, ROLES
except ImportError:  # run as a script by the engine's Python
    from engineapi import KIND_ROLES, REQUESTS, ROLES


def _name(f: dataclasses.Field) -> str:
    return str(f.metadata.get("wire", f.name))


def wire(value: Any) -> Any:
    """A dataclass (nested) as plain JSON values: tuples become lists."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {_name(f): wire(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, (list, tuple)):
        return [wire(v) for v in value]
    if isinstance(value, dict):
        return {k: wire(v) for k, v in value.items()}
    return value


def _convert(hint: Any, value: Any, at: str) -> Any:
    origin, args = typing.get_origin(hint), typing.get_args(hint)
    if hint is Any:
        return value
    if origin in (typing.Union, types.UnionType):
        if value is None and type(None) in args:
            return None
        arm = next(a for a in args if a is not type(None))   # the types here are `X | None` alone
        return _convert(arm, value, at)
    if dataclasses.is_dataclass(hint):
        return parse(hint, value, at)
    if origin is list and isinstance(value, list):
        return [_convert(args[0], v, f"{at}[{i}]") for i, v in enumerate(value)]
    if origin is tuple and isinstance(value, (list, tuple)) and len(args) == 2 and args[1] is Ellipsis:
        return tuple(_convert(args[0], v, f"{at}[{i}]") for i, v in enumerate(value))   # `tuple[X, ...]`
    if origin is tuple and isinstance(value, (list, tuple)) and len(args) == len(value):
        return tuple(_convert(a, v, f"{at}[{i}]") for i, (a, v) in enumerate(zip(args, value, strict=True)))
    if origin is dict and isinstance(value, dict):
        return {str(k): _convert(args[1], v, f"{at}.{k}") for k, v in value.items()}
    if hint is float and isinstance(value, (int, float)) and not isinstance(value, bool):
        return value                                         # a whole number stays one: 4 is sent as 4, not 4.0
    if hint in (str, int, bool) and type(value) is hint:
        return value
    raise ValueError(f"{at}: {type(value).__name__} is not {getattr(hint, '__name__', hint)}")


def parse(cls: type, data: Any, at: str = "") -> Any:
    """`data` (a wire dict) as `cls`: every field checked by its type; an unknown or missing field is refused."""
    name = at or cls.__name__
    if not isinstance(data, dict):
        raise ValueError(f"{name}: an object expected")
    hints = typing.get_type_hints(cls)
    fields = {_name(f): f for f in dataclasses.fields(cls)}
    unknown = sorted(set(data) - set(fields))
    if unknown:
        raise ValueError(f"{name}: unknown field {unknown[0]}")
    missing = [n for n, f in fields.items() if n not in data and f.default is dataclasses.MISSING
               and f.default_factory is dataclasses.MISSING]
    if missing:
        raise ValueError(f"{name}: missing field {missing[0]}")
    return cls(**{fields[k].name: _convert(hints[fields[k].name], v, f"{name}.{k}") for k, v in data.items()})


def request_wire(request: Any) -> dict[str, Any]:
    """A request as it crosses: its fields plus its `kind`."""
    return {"kind": type(request).kind, **wire(request)}


KIND_WORDS = {"image": "picture", "video": "clip", "speech": "line", "join": "join", "voice": "voice",
              "sound": "sound", "frames": "frames"}


def request_parse(data: Any) -> Any:
    """A request from the wire, by its `kind`; one line when it is not one the Hub sends, or when a picture's role is
    not one of `ROLES` or not one its kind takes (`KIND_ROLES`: a picture request's `reference`; a clip's `start`,
    `end`, `source` or `identity`; a line's none)."""
    kind = data.get("kind") if isinstance(data, dict) else None
    if kind not in REQUESTS:
        raise ValueError(f"request: unknown kind {kind!r}")
    request = parse(REQUESTS[kind], {k: v for k, v in data.items() if k != "kind"}, "request")
    for i, ref in enumerate(getattr(request, "references", None) or ()):
        if ref.role not in ROLES:
            raise ValueError(f"request.references[{i}]: unknown role {ref.role!r}")
        if ref.role not in KIND_ROLES[kind]:
            raise ValueError(f"request.references[{i}]: a {KIND_WORDS[kind]} request takes no {ref.role} picture")
    return request
