"""`script_start`'s asks (blueprint A.3 and §7): the context is written first, by the model in Settings →
Assistant, cast from Characters only. The ask carries the context's schema with the cast's names an enum of the
Characters names, held by the backend (`ask(messages, schema)`); a reply `context.read` or
`context.pictured` refuses is sent back with its line once (a second one-line refusal ends
the asks). Nothing of the story or the replies is kept. The names offered are those the story names
(`named`), all when it names none; named as written, case included, or by a name's first word. With
`anyone` (the chat message through `script_say`), the cast is whoever the story names, with a picture or not
(`ANYONE`); every field but a name only from the story's words, else left out; Characters may be empty.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from hub.core.api import Ctx, Invalid

from . import context as scene_context
from .edit import refuse

FIELDS = ("Write a member's look, costume, what of a picture to ignore and home, the set (name, description, elements "
          "and props) and the style only from what the story says, and leave out every field the story says nothing "
          "of; home, when the story places the member, a whole number from 0 to 100, left to right. Answer with JSON "
          "only.")
SYSTEM = "You write the scene context of a story. The story's cast are only these names from Characters: {}. " + FIELDS
ANYONE = ("You write the scene context of a story. The story's cast are the people it names, each by the name it "
          "gives{}. " + FIELDS)
SEND_BACK = ("The Hub refused that context: {}. Send the whole context again as one JSON object, changed only where "
             "needed.")
NO_JSON = "The reply holds no JSON object"
_THINK = re.compile(r"</think\s*>", re.IGNORECASE)
_FENCE = re.compile(r"^\s*```[\w-]*\s*$", re.MULTILINE)


def _text() -> dict:              # not blank, no length cap of the Hub's
    return {"type": "string", "minLength": 1}


def schema(names: list[str], anyone: bool = False) -> dict:
    """The context as a JSON Schema, every cast name one of `names` (`anyone`: any name)."""
    who = _text() if anyone else {"type": "string", "enum": names}
    member = {"type": "object", "additionalProperties": False,
              "required": ["name"],
              "properties": {"name": who, "look": _text(), "costume": _text(),
                             "ignore": _text(), "home": {"type": "integer", "minimum": 0, "maximum": 100}}}
    prop = {"type": "object", "additionalProperties": False, "required": ["name"],
            "properties": {"name": _text(), "owner": _text() if anyone else {"type": "string", "enum": names},
                           "description": _text()}}
    stage = {"type": "object", "additionalProperties": False, "required": ["name"],
             "properties": {"name": _text(), "description": _text(),
                            "elements": {"type": "array", "items": _text()},
                            "props": {"type": "array", "items": prop}}}
    return {"type": "object", "additionalProperties": False, "required": ["cast"],
            "properties": {"cast": {"type": "array", "minItems": 0, "items": member},
                           "set": stage, "style": _text()}}


def _close(text: str, start: int) -> int | None:
    depth, quoted, escaped = 0, False, False
    for i in range(start, len(text)):
        c = text[i]
        if quoted:
            escaped, quoted = (False, True) if escaped else (c == "\\", c != '"')
            continue
        if c == '"':
            quoted = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
    return None


def read_reply(reply: str) -> Any:
    """The first balanced {...} that parses as an object, after any </think> and without fence lines; else None."""
    text = _FENCE.sub("", _THINK.split(reply)[-1])
    at = text.find("{")
    while at != -1:
        end = _close(text, at)
        if end is None:
            return None
        try:
            found = json.loads(text[at:end + 1])
        except ValueError:
            found = None
        if isinstance(found, dict):
            return found
        at = text.find("{", end + 1)
    return None


def named(story: str, names: list[str]) -> list[str]:
    """Pass 1, each name as written, case included, a whole word
    (`context.mention`), longest first, each found blanked (so "Character 1 Two" takes its words before "Character 1");
    pass 2, on what is left, a name of more than one word not found by its first word alone (`context.first_word`: not
    itself one of `names`, not an article), every name sharing it. In `names`' order; every name when it names none."""
    left, found = story, set()
    for name in sorted(names, key=len, reverse=True):
        pattern = scene_context.mention(name)
        if pattern.search(left):
            found.add(name)
            left = pattern.sub(" ", left)
    for name in names:
        word = scene_context.first_word(name, names)
        if name not in found and word is not None and scene_context.mention(word).search(left):
            found.add(name)
    return [n for n in names if n in found] or list(names)


async def context(ctx: Ctx, story: str, characters: Mapping[str, str], names: list[str], anyone: bool = False) -> dict:
    """The context the model wrote for `story`, `context.read` held; else the refusal after the second refused reply."""
    if anyone:                                           # only the names it names: no fallback to all of them
        hit = named(story, names) if names else []
        names = hit if any(scene_context.mention(n).search(story) or (w := scene_context.first_word(n, names)) and
                           scene_context.mention(w).search(story) for n in hit) else []
    elif not names:
        raise refuse("Characters holds no picture", "Put a picture of each of the cast in Characters, then call "
                     "script_start again", characters=[])
    names = names if anyone else named(story, names)
    held = schema(names, anyone)
    told = ANYONE.format(f"; these have a picture in Characters: {', '.join(names)}" if names else "") if anyone \
        else SYSTEM.format(", ".join(names))
    from . import saystory  # late: saystory reads this module

    sent = [{"role": "system", "content": told},
            {"role": "user", "content": saystory.USER.format(story)}]
    line, before, refused = "", None, 0
    while True:
        try:
            _, reply = await ctx.service("ask")(sent, held)
        except Invalid as e:
            raise refuse(e.text, "Set the model in Settings → Assistant, then call script_start again") from None
        value = read_reply(reply)
        try:
            if value is None:
                raise Invalid("context", NO_JSON)
            scene_context.read(value, characters)
            if not anyone:
                scene_context.pictured(value, characters)  # a new context is cast from Characters only
            return value
        except Invalid as e:
            line, refused = e.text, refused + 1
            if before is not None:                       # a one-line refusal is sent back once
                break
            before = 1
            sent = [*sent, {"role": "assistant", "content": reply}, {"role": "user", "content": SEND_BACK.format(line)}]
    raise refuse(f"The context was refused {refused} times: {line}", "Call script_start again")
