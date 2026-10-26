"""A change by asking: the request's words read as one of three verbs and a place, and the set record
with it applied. Pure: no file, no job.

`parse(words, record)` -> `{op, thing, place, words}`. The verb opens the sentence: `add|put|place|set|bring` is `add`,
except `put|place|set` of a thing the record already holds with a place (a prop), which is `move`; `move|shift|slide` is
`move`; `remove|delete|take away|take out|get rid of` is `remove`; anything else is `other` (the whole sentence is the
change, `thing` and `place` None). `thing` is the words after the verb up to a place, a leading `in|on|into` and
articles dropped. A place begins at a preposition (`at|on|to|in|toward|towards`) or at a place phrase; after an optional
preposition and `the`: `stage left` is `stage_left`, `stage right` `stage_right`, `centre stage`, `centre` or `the
middle` `centre`; bare `left` (`camera left`, `screen left`) is `stage_right` and bare `right` is `stage_left`, as
they read on the plates (stage left is the house's right: R53's frame, stage left = +x); `upstage` or `at the back`
is depth `upstage`, `downstage` or `at the front` `downstage`. Place words that match none are kept as `words` with
`side` and `depth` None. `Place.words` is the words written for the place, a leading `to|toward|towards` dropped
("stage left", "at the back").

`apply(record, op)` -> a new record: `add` puts `{name, place}` in `props` (its place replaced when it is there);
`move` of a prop sets its place, of an element moves it from `elements` into `props` with that place, of an unknown
thing adds it; `remove` drops it from either list (unknown: nothing); every op appends `words` to `changes`. A thing
matches a record name case-folded, articles ignored and a final "s" ignored. Every other key is kept as it was.
"""
from __future__ import annotations

import copy
import re
from typing import Any

VERBS = (("get rid of", "remove"), ("take away", "remove"), ("take out", "remove"), ("remove", "remove"),
         ("delete", "remove"), ("move", "move"), ("shift", "move"), ("slide", "move"), ("add", "add"),
         ("put", "add"), ("place", "add"), ("set", "add"), ("bring", "add"))
PLACING = ("put", "place", "set")          # of a thing held with a place: a move
ARTICLES = ("a", "an", "the", "some")
LEADING = ("in", "on", "into")               # a preposition right after the verb, before the thing
PREPOSITIONS = ("at", "on", "to", "in", "toward", "towards")
SIDES = (("stage left", "stage_left"), ("stage right", "stage_right"), ("centre stage", "centre"),
         ("center stage", "centre"), ("camera left", "stage_right"), ("screen left", "stage_right"),
         ("camera right", "stage_left"), ("screen right", "stage_left"), ("middle", "centre"),
         ("centre", "centre"), ("center", "centre"), ("left", "stage_right"), ("right", "stage_left"))
DEPTHS = (("upstage", "upstage"), ("downstage", "downstage"), ("back", "upstage"), ("front", "downstage"))
NO_PLACE: dict[str, Any] = {"words": "", "side": None, "depth": None}


def _words(text: str) -> list[str]:
    return re.findall(r"[\w'-]+", text.casefold())


def _starts(tokens: list[str], phrase: str) -> bool:
    want = phrase.split()
    return tokens[:len(want)] == want


def _core(tokens: list[str]) -> list[str]:
    """A place's words after an optional preposition and `the`."""
    rest = tokens[1:] if tokens and tokens[0] in PREPOSITIONS else tokens
    return rest[1:] if rest and rest[0] == "the" else rest


def _is_place(tokens: list[str]) -> bool:
    core = _core(tokens)
    return tokens[0] in PREPOSITIONS or any(_starts(core, p) for p, _ in (*SIDES, *DEPTHS))


def _find(core: list[str], table: tuple[tuple[str, str], ...]) -> str | None:
    for i in range(len(core)):
        for phrase, value in table:
            if _starts(core[i:], phrase):
                return value
    return None


def place_of(tokens: list[str], written: str) -> dict[str, Any]:
    """The place from its words (`tokens`, case-folded) and as written (`written`)."""
    core = _core(tokens)
    words = re.sub(r"^(to|toward|towards)\s+", "", written, flags=re.IGNORECASE).strip()
    return {"words": words, "side": _find(core, SIDES), "depth": _find(core, DEPTHS)}


def key(name: Any) -> str:
    """A name as it matches: case-folded, articles dropped, a final "s" dropped."""
    tokens = [t for t in _words(str(name or "")) if t not in ARTICLES]
    text = " ".join(tokens)
    return text[:-1] if text.endswith("s") else text


def _prop(record: dict[str, Any], thing: str) -> dict[str, Any] | None:
    props = record.get("props") if isinstance(record.get("props"), list) else []
    return next((p for p in props if isinstance(p, dict) and key(p.get("name")) == key(thing)), None)


def parse(words: str, record: dict[str, Any]) -> dict[str, Any]:
    """`words` as `{op, thing, place, words}` (the module docstring)."""
    said = " ".join(str(words or "").split())
    tokens = _words(said)
    verb = next(((v, op) for v, op in VERBS if _starts(tokens, v)), None)
    if verb is None:
        return {"op": "other", "thing": None, "place": None, "words": said}
    phrase, op = verb
    rest = tokens[len(phrase.split()):]
    if rest and rest[0] in LEADING:                 # "bring in a piano": the thing is the piano
        rest = rest[1:]
    while rest and rest[0] in ARTICLES:
        rest = rest[1:]
    cut = next((i for i in range(1, len(rest)) if _is_place(rest[i:])), len(rest))
    thing_tokens, place_tokens = rest[:cut], rest[cut:]
    written = _written(said, place_tokens)
    place = place_of(place_tokens, written) if place_tokens else None
    thing = _written(said, thing_tokens, last=False) if thing_tokens else ""
    if op == "add" and phrase in PLACING and _prop(record, thing) is not None:
        op = "move"
    return {"op": op, "thing": thing, "place": place, "words": said}


def _written(said: str, tokens: list[str], last: bool = True) -> str:
    """`tokens` as written in `said` (their case kept): the sentence's last (or first) run of them."""
    if not tokens:
        return ""
    pattern = r"\W+".join(re.escape(t) for t in tokens)
    found = list(re.finditer(pattern, said, flags=re.IGNORECASE))
    if not found:
        return " ".join(tokens)
    return (found[-1] if last else found[0]).group(0)


def apply(record: dict[str, Any], op: dict[str, Any]) -> dict[str, Any]:
    """The record with `op` applied (the module docstring); the given record is not changed."""
    out = copy.deepcopy(record)
    elements = [e for e in out.get("elements") or [] if isinstance(e, str)]
    props = [p for p in out.get("props") or [] if isinstance(p, dict)]
    thing, place = op.get("thing") or "", op.get("place") or dict(NO_PLACE)
    held = next((p for p in props if key(p.get("name")) == key(thing)), None)
    element = next((e for e in elements if key(e) == key(thing)), None)
    if op.get("op") == "add" and thing:
        if held is not None:
            held["place"] = place
        else:
            props.append({"name": thing, "place": place})
    elif op.get("op") == "move" and thing:
        if held is not None:
            held["place"] = place
        elif element is not None:
            elements.remove(element)
            props.append({"name": element, "place": place})
        else:
            props.append({"name": thing, "place": place})
    elif op.get("op") == "remove" and thing:
        elements = [e for e in elements if key(e) != key(thing)]
        props = [p for p in props if key(p.get("name")) != key(thing)]
    out.update(elements=elements, props=props,
               changes=[*(c for c in out.get("changes") or [] if isinstance(c, str)), str(op.get("words") or "")])
    return out
