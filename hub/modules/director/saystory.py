"""A new story in two passes. Pass 1, the Assistant model in one schema-held ask: only
the story, as a shot list in film terms (`schema`, `messages`): a title, the length the message names when it names one,
and per shot its framing, who is on, its action, its seconds (the planner's own), its sound (words, or empty) and its
lines (speaker and words, only when someone speaks). Its checks, each sent back to pass 1 with its reason within the ask
limit (`problems`): every shot has an action; neighbouring shots differ in framing; seconds up to `HOLD_MAX_S`; and the
quoted words, numbers and counts as everywhere (`saycheck.check`). Pass 2, Hub code and no model (`operations`): the
shot list as the script exactly as written (the cast from the names, one scene, each shot with its action and seconds,
its lines, its sound as a cue of the kind the planner named, effect when none), run as the ordinary calls
(`saytrial.trial`). The model never writes tool operations for a new story. The Hub never sets, divides, stretches, pads
or defaults a length, and never adds a shot: a shot list still failing at the last ask writes nothing (`asks` returns a
trial with no calls).
"""
from __future__ import annotations

import asyncio
import copy
from typing import Any

from hub.core.api import Ctx, Invalid, schema_check

from . import sayask, saycheck, saytrial, scriptshape
from . import start as begin
from .layout import HOLD_MAX_S, held_seconds

SEND_BACK = ("The Hub sent that shot list back: {}. Send the whole shot list again as one JSON object, changed only "
             "where needed.")
USER = "Story: {}"
RULES = (
    "You plan a new story from the chat message as a shot list in film terms, and nothing else. Answer with JSON "
    'only: {"title": "<the story\'s title>", "seconds": <the whole length>, "shots": [{"framing": "...", "on": '
    '[...], "action": "...", "seconds": <n>, "sound": "...", "sound_kind": "...", "lines": [{"speaker": "...", '
    '"words": "..."}]}]}. '
    "seconds at the top: the story's whole length, only when the message names one, as written. "
    "Each shot: "
    "framing, a few words (wide, medium, close-up, over-the-shoulder, insert, reaction, or another film term); on, "
    "who is in frame, by the names listed; action, what we see happen in it (who does what, the expression, the "
    "movement, the beat), in the story's own events, never a camera word alone; seconds, how long the shot is held, "
    f"up to {HOLD_MAX_S:g}, whole or tenths, your own choice for that shot; sound, what we hear in it, or an empty "
    "string; sound_kind, effect, music or reaction, for that sound; lines, only where someone speaks: the speaker "
    "and the speaker's own words acting on the other, never the "
    "narration copied. The craft: establish the place and who is there first, then go closer; vary the framing, two "
    "neighbouring shots never the same framing; cut on action and on the story's beats; pace each shot's length by "
    "its moment, a long hold for a slow or quiet moment, a quick cut for a sudden beat, never an equal share of the "
    "length; build to a turn and an end. The shots' seconds add up to the length the message names. The "
    "message's quoted words exactly as written; a count the message writes is kept.")


def _text(lo: int) -> dict:       # no length cap of the Hub's
    return {"type": "string", "minLength": lo}


def schema(cast: list[str]) -> dict:
    """Pass 1's schema: `on` and a line's `speaker` the context's names (any name when the context names none)."""
    name = {"type": "string", "enum": list(cast)} if cast else _text(1)
    line = {"type": "object", "additionalProperties": False, "required": ["speaker", "words"],
            "properties": {"speaker": name, "words": _text(1)}}
    shot = {"type": "object", "additionalProperties": False,
            "required": ["framing", "on", "action", "seconds", "sound"], "properties": {
                "framing": _text(1), "on": {"type": "array", "items": name},
                "action": _text(0), "seconds": {"type": "number"}, "sound": _text(0),
                "sound_kind": {"type": "string", "enum": list(scriptshape.CUES)},
                "lines": {"type": "array", "items": line}}}
    return {"type": "object", "additionalProperties": False, "required": ["title", "shots"], "properties": {
        "title": _text(1), "seconds": {"type": "integer", "minimum": 1},
        "shots": {"type": "array", "minItems": 1, "items": shot}}}


def messages(script: dict, words: str) -> list[dict]:
    cast = [f"- {line}" for line in sayask._context(script)] or ["- no one listed: name each one as the story does"]
    return [{"role": "system", "content": RULES + "\n\nThe names and the place:\n" + "\n".join(cast)},
            {"role": "user", "content": USER.format(words)}]


def send_back(reply: str, lines: list[str]) -> list[dict]:
    return [{"role": "assistant", "content": reply}, {"role": "user", "content": SEND_BACK.format("; ".join(lines))}]


def _framing(shot: dict) -> str:
    return " ".join(str(shot.get("framing", "")).casefold().split())


def _which(ks: list[int], what: str) -> str:
    return f"shot {ks[0]} has {what}" if len(ks) == 1 else f"shots {', '.join(map(str, ks))} have {what}"


def _seconds(shot: dict) -> Any:
    v = shot.get("seconds")
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def problems(value: Any) -> list[str]:
    """Pass 1's checks on a reply, each line its reason; [] when the shot list holds."""
    shots = value.get("shots") if isinstance(value, dict) else None
    if not isinstance(shots, list) or not shots or not all(isinstance(s, dict) for s in shots):
        return ["the reply holds no shot list: send shots, each with its framing, on, action, seconds and sound"]
    out = []
    bare = [k for k, s in enumerate(shots, 1) if not (isinstance(s.get("action"), str) and s["action"].strip())]
    if bare:
        out.append(f"{_which(bare, 'no action')}: write what we see happen in it")
    same = [k for k in range(2, len(shots) + 1) if _framing(shots[k - 2]) == _framing(shots[k - 1])]
    if same:
        out.append(f"shots {', '.join(f'{k - 1} and {k}' for k in same)} have the same framing: neighbouring shots "
                   "differ in framing")
    wild = [k for k, s in enumerate(shots, 1) if _seconds(s) is None or not held_seconds(_seconds(s))]
    if wild:
        out.append(f"{_which(wild, 'seconds')} a shot cannot hold (more than 0, up to {HOLD_MAX_S:g} s, whole or "
                   "tenths): hold each shot as long as its moment needs")
    return out


def operations(value: dict, cast: list[str]) -> list[dict]:
    """Pass 2, no model: the shot list as the script's operations, exactly as written (`cast` the context's names)."""
    shots, held = value["shots"], {n.casefold() for n in cast}
    seen: dict[str, str] = {}
    for n in (n for s in shots for n in [*s.get("on", []), *(ln["speaker"] for ln in s.get("lines", []))]):
        seen.setdefault(n.casefold(), n)                 # each name once, as first written
    names = list(seen.values())
    out: list[dict] = [{"op": "cast", "name": n} for n in names if n.casefold() not in held]
    out.append({"op": "add_scene", "title": value["title"], **({"cast": names} if names else {}),
                **({"seconds": value["seconds"]} if "seconds" in value else {})})
    for shot in shots:
        out.append({"op": "add_shot", "framing": shot["framing"], "on": list(shot.get("on", [])),
                    "action": shot["action"], "seconds": shot["seconds"]})
        out += [{"op": "add_line", "speaker": ln["speaker"], "words": ln["words"]} for ln in shot.get("lines", [])]
        if shot.get("sound", "").strip():
            out.append({"op": "add_cue", "cue": shot.get("sound_kind") or "effect", "words": shot["sound"]})
    return out


async def asks(ctx: Ctx, base: dict, words: str, setup: tuple) -> saytrial.Tried:
    """Pass 1 while the model mends (a refused reply is sent back when it is the first or has fewer
    reasons than the one before; one with as many or more is the last), each reply checked, then pass 2 on a trial; a
    trial with no calls when the last reply still fails (nothing is written)."""
    characters, names, pace, samples = setup
    cast = [m["name"] for m in base["context"]["cast"]]
    held, bare = schema(cast), sayask.bare(base)
    sent, lines, before = messages(base, words), [], None
    while True:
        try:
            _, reply = await ctx.service("ask")(sent, held)
        except Invalid as e:
            lines = [saytrial.NO_MODEL if e.field == "model" else e.text]
            break
        value, tried, whole = begin.read_reply(reply), None, False
        lines = problems(value) if value is not None else [begin.NO_JSON]
        if not lines:
            try:
                schema_check(held, value)
            except Invalid as e:
                lines = [e.text]
        said = set(saycheck.lengths(words))
        if not lines and "seconds" not in value and len(said) == 1 and 1 <= (n := said.pop()):
            value["seconds"] = round(n)                  # the length the message names, as written
        if not lines:
            ops, lines, _ = saycheck.check({"title": value["title"], "operations": operations(value, cast)}, words,
                                           bare, True)              # the message's quoted words, numbers, counts
        if not lines:
            tried = await asyncio.to_thread(saytrial.trial, base, {}, list(enumerate(ops, 1)), words, True,
                                            characters, names, pace, samples, False)
            whole = len(tried.applied) == len(ops)       # every operation as written, none refused
            tried.title, lines = value["title"], list(tried.kept)
        last = before is not None and len(lines) >= before
        if tried is not None and whole and (not lines or last):
            return tried                                 # written; a gap left is said in its line
        if last:
            break
        before, sent = len(lines), [*sent, *send_back(reply, lines)]
    out = saytrial.Tried(copy.deepcopy(base), True)
    out.kept = lines or ["nothing came back"]
    return out
