"""What a module can do, published as MCP tools: generated from its declarations, never hand-written per feature.

A `Screen` becomes `get_<id>_settings` and `set_<id>_settings`, the set schema built from its `Setting`s; a
`Listing` becomes `list_<name>`; an `Action` is published under its own name. Every description is a plain factual
label made from the module's title, the setting names and the declared texts; none says when to call a tool
(except the `Script:` sentence of three Generate actions, and the script tools' field words).
"""
from __future__ import annotations

import copy
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from hub.core.api import Action, Ctx, Listing, Module, Screen, Setting

NO_ARGS: dict = {"type": "object", "properties": {}, "additionalProperties": False}


@dataclass(frozen=True)
class Tool:
    """An MCP tool as the core serves it (`hub/core/mcp.py`): the generated form of a module's declaration."""
    name: str
    description: str
    input_schema: dict
    fn: Callable[[Ctx, dict], Awaitable[dict]]


def lora_schema(lo: float, hi: float) -> dict:
    """One entry of a `loras` setting: the LoRA's id and its strength within the setting's bounds. `file` is what
    the get tool reports beside the id; handed back as it came, it is taken and not read."""
    return {"type": "object", "additionalProperties": False, "required": ["id", "strength"],
            "properties": {"id": {"type": "string", "minLength": 1},
                           "strength": {"type": "number", "minimum": lo, "maximum": hi},
                           "file": {"type": "string", "readOnly": True,
                                    "description": "The file inside the model's folder, as get reports it"}}}


def value_schema(s: Setting) -> dict:
    """The JSON Schema of one setting's value, from its kind, choices, bounds and text. A `seed` and a `loras`
    setting carry their bounds in `lo` and `hi` (the registry sees to it); a `text` setting its length in `hi`."""
    out: dict = {"type": "string"}
    text = s.text
    if s.kind == "text" and s.hi is not None:
        out["maxLength"] = int(s.hi)
    if s.kind in ("number", "integer"):
        out = {"type": s.kind}
        if s.lo is not None:
            out["minimum"] = s.lo
        if s.hi is not None:
            out["maximum"] = s.hi
    elif s.kind == "loras":
        out = {"type": "array", "items": lora_schema(s.lo or 0, s.hi or 0)}
    elif s.kind == "names":
        name = {"type": "string", "minLength": 1, "maxLength": 120}
        out = {"type": "array", "maxItems": int(s.hi or 0), "items": name}
    elif s.kind == "object":
        out = copy.deepcopy(dict(s.schema or {}))
    elif s.kind == "seed":
        out = {"type": "string", "minLength": 1, "maxLength": len(str(int(s.hi or 0)))}
        form = f"random, or a whole number from {int(s.lo or 0)} to {int(s.hi or 0)}"
        text = f"{s.text}: {form}" if s.text else form
    if s.choices:
        out["enum"] = list(s.choices)
    if text:
        out["description"] = text
    return out


def _screen_tools(mod: Module, screen: Screen) -> list[Tool]:
    ident = mod.id.replace("-", "_")
    names = ", ".join(s.name for s in screen.settings)

    async def get(ctx: Ctx, args: dict) -> dict:
        return await screen.read(ctx)

    async def set_(ctx: Ctx, args: dict) -> dict:
        return await screen.write(ctx, args)

    schema = {"type": "object", "additionalProperties": False,
              "properties": {s.name: value_schema(s) for s in screen.settings}}
    return [Tool(f"get_{ident}_settings", f"Settings of the {mod.title} screen: {names}.", NO_ARGS, get),
            Tool(f"set_{ident}_settings",
                 f"Set settings of the {mod.title} screen: {names}. Returns the settings after.", schema, set_)]


def _listing_tool(listing: Listing) -> Tool:
    schema: dict = {"type": "object", "additionalProperties": False, "properties": dict(listing.args)}
    if listing.required:
        schema["required"] = list(listing.required)
    return Tool(f"list_{listing.name}", listing.text, schema, listing.fn)


def _action_tool(action: Action) -> Tool:
    return Tool(action.name, action.text, action.schema, action.fn)


def tools_of(mod: Module) -> list[Tool]:
    """Every tool a module publishes: its screen's get and set, its listings, its actions, in that order."""
    out = _screen_tools(mod, mod.screen) if mod.screen is not None else []
    out += [_listing_tool(x) for x in mod.listings]
    out += [_action_tool(a) for a in mod.actions]
    return out
