"""The cue and room takes of Track (blueprint §12.1, §12.3; R48 §6): every cue of
a locked script whose take is none, stale or gone from Sounds rendered as one take on the sound model for its kind,
and the room (the set's own tone, under everything) as one ambience take. The models are Generate's pick by the
catalog's mark (its `cue` service, `generate_image/tools.cue_pick`); none is named here.

A cue kind with no sound model is left out, its cues no task,
and said in one line (`<kind> left out: <the pick's line>`), as the room is without its model (`room_note`); the lines
never wait on a cue model. The same pick decides at the mix (`left`). The tasks go by model, each model
once per job (`plan`). The room's prompt (the set's name and description alone) is computed from the
context at each press, never stored; its take is keyed `room` in `takes`, its hash over the set's name and
description (`audioscript.sound_hash`'s form), so a longer script does not render it again (the mix loops it).
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field

from hub.core.api import Ctx, Invalid, SoundRequest, request_wire

from . import audioscript, layout, scriptshape
from .render import _words

ROOM_ID = "room"                 # names no event: an event id is a letter and a number (`edit.py`)
ROOM_MIN_S, ROOM_OVER = 10, 1.25  # at least 10 s; a quarter more than the planned length
NO_WORDS = "the set has no name or description"   # nothing to send, no room task
NO_GENERATE = "Generate Image is not running"
LEFT_OUT = "room tone left out: "


@dataclass
class More:
    """What the cues and the room add to a Track job, in task order: each one task in its own one-take group."""
    tasks: list[dict] = field(default_factory=list)
    ids: list[str] = field(default_factory=list)
    kinds: list[str] = field(default_factory=list)      # each task's cue kind, or "room"
    hashes: dict[str, str] = field(default_factory=dict)
    seeds: list[int] = field(default_factory=list)      # none sent, so none listed
    models: list[tuple[str, str]] = field(default_factory=list)   # (id, label) of each task's model
    notes: list[str] = field(default_factory=list)      # a line per kind left out, then the room's
    cues: int = 0
    room: bool = False

    @property
    def note(self) -> str | None:
        """The notes as one text (the answer's and the record's), None when there is none."""
        return "; ".join(self.notes) or None


def room_hash(script: dict) -> str:
    """`audioscript.sound_hash`'s form over `["room", set name, set description]`."""
    stage = script.get("context", {}).get("set") or {}
    fields = ["room", stage.get("name") or "", stage.get("description") or ""]
    raw = json.dumps(fields, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def room_note(text: str) -> str:
    """The answer's line when the room's sound model is not there."""
    return LEFT_OUT + text


def room_why(ctx: Ctx, there: str) -> str:
    """The room note's why: `there` when the room's model is there, else the pick's line."""
    try:
        return _pick(ctx, ROOM_ID) and there
    except Invalid as e:
        return e.text


def _pick(ctx: Ctx, kind: str) -> dict:
    try:
        pick = ctx.service("cue")
    except Invalid:
        raise Invalid("model", NO_GENERATE) from None
    return pick(kind)


def _held(lo: int, hi: int, seconds: int) -> int:
    return min(hi, max(lo, seconds))


def _cues(script: dict) -> list[dict]:
    rows = [ev for shot in layout.shots(script) for ev in shot["events"] if ev["kind"] == "cue"]
    return sorted(rows, key=lambda ev: (ev["start_ms"], ev["id"]))


def _picks(ctx: Ctx, name: str, script: dict, takes: dict, there: set[str]) -> tuple[list[dict], dict, dict]:
    """The cues with no current take, in time order; one pick per kind -> (cues, {kind: model}, {kind: its line
    `<kind> left out: <the pick's line>`}, kinds in the order of their first cue)."""
    todo = [ev for ev in _cues(script)
            if audioscript.take(name, ev, takes, present=there)["state"] in ("none", "stale")]
    picks: dict[str, dict] = {}
    left: dict[str, str] = {}
    for ev in todo:
        if ev["cue"] not in picks and ev["cue"] not in left:
            try:
                picks[ev["cue"]] = _pick(ctx, ev["cue"])
            except Invalid as e:
                left[ev["cue"]] = f"{ev['cue']} left out: {e.text}"
    return todo, picks, left


def left(ctx: Ctx, name: str, script: dict, takes: dict, there: set[str]) -> tuple[list[str], set[str]]:
    """At the mix: (the left-out lines, kinds in first-cue order; the ids of the cues left out), the cues with no
    current take whose kind's pick refuses now."""
    todo, _, lines = _picks(ctx, name, script, takes, there)
    return list(lines.values()), {ev["id"] for ev in todo if ev["cue"] in lines}


def _room(ctx: Ctx, script: dict, takes: dict, there: set[str], more: More) -> tuple | None:
    """The room's (model, prompt, seconds, hash) when `takes.room` is absent, its file gone or its hash not the
    context's; without its sound model None and its note, the press not refused (an existing room take left as is).
    Its prompt is the set's name and description as typed, whitespace closed up, joined by `render._words`, nothing
    of the Hub's; a set with neither: None and its note."""
    held, want = takes.get(ROOM_ID), room_hash(script)
    if held is not None and held.get("file") in there and held.get("hash") == want:
        return None
    try:
        model = _pick(ctx, ROOM_ID)
    except Invalid as e:
        more.notes.append(room_note(e.text))
        return None
    stage = script.get("context", {}).get("set") or {}
    prompt = _words(*(str(stage.get(k) or "") for k in ("name", "description")))
    if not prompt:                       # an empty prompt is not sent
        more.notes.append(room_note(NO_WORDS))
        return None
    planned = math.ceil(ROOM_OVER * scriptshape.length_ms(script) / 1000)
    return model, prompt, _held(int(model["seconds"]["min"]), int(model["seconds"]["max"]), max(ROOM_MIN_S, planned)), \
        want


def _add(more: More, ident: str, kind: str, model: dict, prompt: str, seconds: int, hashed: str) -> None:
    more.tasks.append(request_wire(SoundRequest(model["id"], prompt, None, seconds, measure=True,
                                                decay=kind == "reaction")))
    more.ids.append(ident)
    more.kinds.append(kind)
    more.hashes[ident] = hashed
    more.models.append((model["id"], model["label"]))


def plan(ctx: Ctx, name: str, script: dict, takes: dict, there: set[str], speech: str | None = None) -> More:
    """The cue and room tasks by model, each model once: the speech model (`speech`, the
    lines' own, which run first) when a cue or the room uses it, then each cue model in the order of its first cue,
    then the room's when no cue uses it; within a model its cues in time order, then the room. A kind with no model:
    its cues left out, one line each in `notes`, then the room's."""
    more = More()
    todo, picks, lines = _picks(ctx, name, script, takes, there)
    kept = [ev for ev in todo if ev["cue"] in picks]
    more.notes.extend(lines.values())
    room = _room(ctx, script, takes, there, more)
    order = dict.fromkeys([*([speech] if speech else []), *(picks[ev["cue"]]["id"] for ev in kept),
                           *([room[0]["id"]] if room else [])])
    for model_id in order:
        for ev in (ev for ev in kept if picks[ev["cue"]]["id"] == model_id):
            model = picks[ev["cue"]]
            seconds = _held(int(model["seconds"]["min"]), int(model["seconds"]["max"]), audioscript.cap(ev))
            _add(more, ev["id"], ev["cue"], model, ev["words"], seconds, audioscript.sound_hash(ev))
        if room is not None and room[0]["id"] == model_id:
            _add(more, ROOM_ID, ROOM_ID, room[0], room[1], room[2], room[3])
            more.room = True
    more.cues = len(kept)
    return more


def _count(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def answer(name: str, got: dict) -> list[str]:
    """`<name> · Track: 4 lines, 3 cues and the room rendering, up to 3 takes per line (job <id>)`, then one line
    per kind left out and the room's (at most 1 + 3 + 1 lines)."""
    parts = [_count(got["lines"], "line")] if got["lines"] else []
    parts += [_count(got["cues"], "cue")] if got["cues"] else []
    parts += ["the room"] if got["room"] else []
    said = ", ".join(parts[:-1]) + " and " + parts[-1] if len(parts) > 1 else parts[0]
    per = f", up to {got['takes']} takes per line" if got["lines"] else ""
    first = f"{name} · Track: {said} rendering{per} (job {got['job']})"
    return [first, *got.get("notes", [])]
