"""The scene context of a version-2 script (blueprint §2, R48 §8): each cast member's look, costume, what
to ignore and home place; the set with its elements and props; the style line. `read(context, characters, where)` gives
`{folded name -> name}` of the cast when every check holds, else one `Invalid` line naming where ("Context, cast
Character 1: …", "Context, set, prop Prop 1: …"). Look, costume, ignore, home, the set, its description and the style
are optional here: a context being written reads; "context incomplete" is the lock's (Step 7, blueprint A.7).
A member whose name has no picture in Characters reads (the Characters folder is not written); `unpictured`
names them, `pictured` refuses the first (a new context is cast from Characters only, `start.context`).
`mention` and `first_word`, the one rule by which a story (`start.named`) and a camera (`frame._rename`)
name a member: as written, case included, a whole word; a name's first word alone when no other name claims it.
A member needs no picture and no voice; `picture_use` says how the member's picture is used
(`PICTURE_USES`: as identity, as the first frame, not at all), and `picture_use()` is what a shot uses: `none` with no
picture, else the member's word, `reference` by default.
"""
from __future__ import annotations

import re
from collections.abc import Container, Iterable
from typing import Any

from hub.core.api import Invalid

CONTEXT = (("cast",), ("set", "style"))
MEMBER = (("name",), ("look", "costume", "ignore", "home", "picture_use"))
PICTURE_USES = ("reference", "frame", "none")
SET = (("name",), ("description", "elements", "props", "plate"))
PROP = (("name",), ("owner", "description"))
ARTICLES = frozenset({"the", "a", "an"})


def _no(where: str, text: str) -> Invalid:
    return Invalid("script", f"{where}: {text}")


def _keys(value: Any, keys: tuple[tuple[str, ...], tuple[str, ...]], where: str, what: str) -> dict:
    need, may = keys
    if not isinstance(value, dict):
        raise _no(where, f"{what} is not an object")
    missing = [k for k in need if k not in value]
    if missing:
        raise _no(where, f"{what} has no {missing[0]}")
    extra = sorted(set(value) - set(need) - set(may))
    if extra:
        raise _no(where, f"{what} has a key the format does not know: {extra[0]}")
    return value


def _text(value: Any, where: str, what: str) -> str:
    """Typed text: not blank, any length."""
    if not isinstance(value, str) or not value.strip():
        raise _no(where, f"{what} is text, not blank")
    return value


def _named(value: Any, where: str, what: str, n: int) -> str:
    """The item's `where`: by its name when the name is text, else by its place in the list."""
    name = value.get("name") if isinstance(value, dict) else None
    return f"{where}, {what} {name}" if isinstance(name, str) and name.strip() \
        else f"{where}, {what} {n}"


def _member(value: Any, where: str) -> str:
    member = _keys(value, MEMBER, where, "a cast member")
    name = _text(member["name"], where, "the name")
    for key in ("look", "costume", "ignore"):
        if key in member:
            _text(member[key], where, key)
    if "home" in member:
        home = member["home"]
        if not isinstance(home, int) or isinstance(home, bool) or not 0 <= home <= 100:
            raise _no(where, "home is a whole number from 0 to 100")
    if "picture_use" in member and member["picture_use"] not in PICTURE_USES:
        raise _no(where, f"picture_use is one of {', '.join(PICTURE_USES)}")
    return name


def _set(value: Any, cast: dict[str, str], where: str) -> None:
    where = f"{where}, set"
    stage = _keys(value, SET, where, "the set")
    _text(stage["name"], where, "the name")
    if "description" in stage:
        _text(stage["description"], where, "the description")
    elements = stage.get("elements", [])
    if not isinstance(elements, list):
        raise _no(where, "elements is a list")
    for item in elements:
        _text(item, where, "an element")
    props = stage.get("props", [])
    if not isinstance(props, list):
        raise _no(where, "props is a list")
    names: set[str] = set()
    for n, value in enumerate(props, 1):
        at = _named(value, where, "prop", n)
        prop = _keys(value, PROP, at, "a prop")
        name = _text(prop["name"], at, "the name")
        if name.casefold() in names:
            raise _no(at, "another prop has this name")
        names.add(name.casefold())
        owner = prop.get("owner")
        if owner is not None and not isinstance(owner, str):
            raise _no(at, "owner is a cast name or null")
        if owner is not None and owner.casefold() not in cast:
            prop["owner"] = None                         # a prop held by no one in the cast: kept, held by no one
        if "description" in prop:
            _text(prop["description"], at, "the description")
    if stage.get("plate") is not None:
        raise _no(where, "plate is null in this version")


def read(context: Any, characters: Container[str], where: str = "Cast and set") -> dict[str, str]:
    """The cast by its folded name -> the name as written, in the context's order. `characters` (the folded names of
    the pictures in Characters) is not checked here: `unpictured` and `pictured` check it."""
    _keys(context, CONTEXT, where, "the context")
    members = context["cast"]
    if not isinstance(members, list):
        raise _no(where, "the cast is a list")
    cast: dict[str, str] = {}
    for n, value in enumerate(members, 1):
        name = _member(value, _named(value, where, "cast", n))
        if name.casefold() in cast:
            raise _no(f"{where}, cast {name}", f"{name} is in the cast twice")
        cast[name.casefold()] = name
    if "set" in context:
        _set(context["set"], cast, where)
    if "style" in context:
        _text(context["style"], where, "the style")
    return cast


def unpictured(context: dict, characters: Container[str]) -> list[str]:
    """The cast names, in cast order, with no picture in Characters, of a context that reads."""
    return [m["name"] for m in context["cast"] if m["name"].casefold() not in characters]


def picture_use(member: dict, characters: Container[str]) -> str:
    """How a shot uses the member's picture: `none` when Characters holds none of the member, else the
    member's `picture_use`, `reference` when unset."""
    if member["name"].casefold() not in characters:
        return "none"
    return str(member.get("picture_use", "reference"))


def pictured(context: dict, characters: Container[str], where: str = "Cast and set") -> None:
    """Invalid naming the first member with no picture in Characters."""
    for name in unpictured(context, characters):
        raise _no(f"{where}, cast {name}", f"{name} has no picture in Characters")


def mention(*names: str) -> re.Pattern:
    """Any of `names` as written, case included, longest first, not preceded or followed by a
    letter, digit or `_` (no `\\b`: it fails after a name ending in a non-word character, "Dr. No")."""
    alternatives = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)")


def first_word(name: str, taken: Iterable[str]) -> str | None:
    """The first word of a name of more than one word, unless it is one of `taken` (folded compare)
    or "The", "A" or "An"; else None."""
    words = name.split()
    if len(words) < 2:
        return None
    folded = words[0].casefold()
    if folded in ARTICLES or folded in {t.casefold() for t in taken}:
        return None
    return words[0]
