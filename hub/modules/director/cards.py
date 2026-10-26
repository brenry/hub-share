"""The cast and set cards edited by hand (`owner.edit_op`'s "member" and "set"): each field as typed, an
empty one taken off; the Director writes the same fields. What render sends of a card (`render.shot`):
look and costume, the set's name, description, elements and props as typed; Ignore and Home stay on the card."""
from __future__ import annotations

from typing import Any

from hub.core.api import Invalid

MEMBER_FIELDS = ("look", "costume", "ignore", "home")
SET_FIELDS = ("name", "description", "elements", "props", "style")


def _one(text: str) -> str:
    return " ".join(text.split())


def member(script: dict, name: str, field: str, value: str) -> dict:
    cast = (script.get("context") or {}).get("cast") or []
    m = next((m for m in cast if str(m.get("name")).casefold() == name.casefold()), None)
    if m is None:
        raise Invalid("member", f"{name} is not in the cast")
    text = _one(value)
    if not text:
        m.pop(field, None)
    elif field == "home":
        if not text.isdigit() or not 0 <= int(text) <= 100:
            raise Invalid("value", "Home is a whole number from 0 to 100")
        m["home"] = int(text)
    else:
        m[field] = text
    return {"did": f"{m['name']}'s {field} set"}


def set_field(script: dict, field: str, value: str) -> dict:
    context = script.setdefault("context", {"cast": []})
    room: dict[str, Any] = context.setdefault("set", {})
    text = _one(value)
    if field == "style":
        context["style"] = text
        if not text:
            context.pop("style")
    elif field == "elements":
        room["elements"] = [e for e in (_one(x) for x in value.replace("\n", ",").split(",")) if e]
    elif field == "props":                               # one a line, "name: description"; a holder kept by name
        held = {str(p.get("name")).casefold(): p.get("owner") for p in room.get("props") or []}
        props = []
        for row in value.splitlines():
            name, _, said = row.partition(":")
            if _one(name):
                p: dict[str, Any] = {"name": _one(name), "owner": held.get(_one(name).casefold())}
                if _one(said):
                    p["description"] = _one(said)
                props.append(p)
        room["props"] = props
    else:
        room[field] = text
        if not text and field == "description":
            room.pop(field)
    return {"did": f"the set's {field} set"}
