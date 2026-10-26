"""The one place modules are found: every `hub/modules/<folder>/manifest.py` that defines `MODULE`.

Deleting a module's folder removes it (its data folder stays). `modules_disabled` skips one.
A module that fails to import is skipped with one error line; a manifest that breaks the
rules (duplicate ids, unprefixed handlers, unknown kinds, a generated tool name taken twice...) stops the hub
at start.
"""
from __future__ import annotations

import importlib
import os
import re
from collections.abc import Iterable

from hub.core.api import Module, Setting
from hub.core.features import tools_of

ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
NAME = re.compile(r"^[a-z0-9_]{1,40}$")
TOOL = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
KINDS = {"image", "video", "audio", "mask", "text"}
SETTING_KINDS = {"choice", "number", "integer", "text", "loras", "seed", "names", "object"}
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
RESERVED = {"api", "assets", "bus", "cards", "core", "files", "upload", "mcp", "pair", "screen", "settings",
            "thumbs"}
MAX_BODY = 25 * 1024 * 1024  # an image upload; JSON routes stay far below


class RegistryError(Exception):
    """A manifest breaks the module rules; the message names the module and the rule."""


def discover(disabled: Iterable[str] = (), package: str = "hub.modules") -> tuple[list[Module], list[str]]:
    """-> (valid modules in folder order, one error line per module that failed to load)."""
    pkg = importlib.import_module(package)
    folders = sorted({e.name for p in pkg.__path__ for e in os.scandir(p)
                      if e.is_dir() and not e.name.startswith(("_", ".")) and os.path.isfile(f"{e.path}/manifest.py")})
    mods, errors, skip = [], [], set(disabled)
    for folder in folders:
        try:
            manifest = importlib.import_module(f"{package}.{folder}.manifest")
        except Exception as e:
            errors.append(f"hub: module {folder} was not loaded: {type(e).__name__}: {e}")
            continue
        mod = getattr(manifest, "MODULE", None)
        if not isinstance(mod, Module):
            errors.append(f"hub: module {folder} was not loaded: manifest.py has no MODULE")
            continue
        if mod.id not in skip:
            mods.append(mod)
    validate(mods)
    return mods, errors


def _choices_ok(s: Setting) -> bool:
    """A choice takes texts; a number or integer takes numbers; the other kinds take no choices."""
    if s.kind == "choice":
        return all(isinstance(c, str) for c in s.choices)
    if s.kind in ("number", "integer"):
        return all(isinstance(c, (int, float)) and not isinstance(c, bool) for c in s.choices)
    return not s.choices


def _bounds_ok(s: Setting) -> bool:
    """A seed and a loras setting name their bounds (the seed's top, the strength's range) in lo and hi."""
    if s.kind == "names":
        return s.hi is not None and s.hi >= 1
    if s.kind == "object":
        return isinstance(s.schema, dict) and s.schema.get("type") == "object"
    return s.kind not in ("seed", "loras") or (s.lo is not None and s.hi is not None and s.lo < s.hi)


def validate(mods: list[Module]) -> None:
    ids, tools = set(), set()
    for m in mods:
        def fail(rule: str, m: Module = m) -> RegistryError:
            return RegistryError(f"hub: module {m.id}: {rule}")

        if not ID.match(m.id) or m.id in RESERVED:
            raise fail("the id must be kebab-case and not a reserved name")
        if m.id in ids:
            raise fail("another module has the same id")
        ids.add(m.id)
        groups = [g.id for g in m.sockets]
        if len(set(groups)) != len(groups) or not all(NAME.match(g) for g in groups):
            raise fail("socket group ids must be unique snake_case names")
        for g in m.sockets:
            if not g.kinds or set(g.kinds) - KINDS or g.max < 1:
                raise fail(f"socket group {g.id} has unknown kinds or no room")
        routes = [(r.method, r.path) for r in m.routes]
        if len(set(routes)) != len(routes):
            raise fail("two routes share a method and path")
        for r in m.routes:
            if r.method not in METHODS or (r.path and not r.path.startswith("/")) or r.auth not in ("screen", "public"):
                raise fail(f"route {r.method} {r.path!r} has a bad method, path or auth")
            if not 0 < r.body_limit <= MAX_BODY:
                raise fail(f"route {r.path} body_limit must be 1 B to 25 MiB")
        for name in m.handlers:
            if not name.startswith(m.id + ".") or not NAME.match(name[len(m.id) + 1:]):
                raise fail(f"handler {name} must be named {m.id}.<name>")
        for lane in m.lanes:
            if not NAME.match(lane):
                raise fail(f"lane {lane} must be a snake_case name")
        for kind in m.jobs:
            if not NAME.match(kind):
                raise fail(f"job kind {kind} must be a snake_case name")
        if m.screen is not None:
            names = [s.name for s in m.screen.settings]
            if not names or len(set(names)) != len(names) or not all(NAME.match(n) for n in names):
                raise fail("screen settings must have unique snake_case names")
            for s in m.screen.settings:
                if s.kind not in SETTING_KINDS or not _choices_ok(s):
                    raise fail(f"setting {s.name} has an unknown kind, or choices its kind cannot take")
                if not _bounds_ok(s):
                    raise fail(f"setting {s.name} needs its bounds in lo and hi")
        for t in tools_of(m):
            if not TOOL.match(t.name) or t.name in tools or not isinstance(t.input_schema, dict):
                raise fail(f"tool {t.name} must be a unique snake_case name with a schema")
            if not t.description or len(t.description) > 200 or not t.description.endswith("."):
                raise fail(f"tool {t.name} needs a description of at most 200 characters, ending with a period")
            tools.add(t.name)
