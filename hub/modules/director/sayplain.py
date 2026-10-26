"""Plain messages read without a model , pure: the never-wreck
rule and the messages that need no planner.
- `asks_removal`: the message asks to take something out (`REMOVE`). `removals`: the planner's removals (`remove`, a
  `cast` with `remove`) blamed when they do not, so they are sent back and never written (as `saycheck` blames).
- `lost`: the lines a trial would lose that the message does not ask to lose; a result that loses any is not written.
- `done`: a message that only says the script is done or finished: every scene said done, no model asked.
- `VAGUE`: the Hub's one sentence of what it can do, for a message that names nothing to change (the planner sends no
  operation, or none survives the checks). `NO_STORY`: a done message with no script open.
- `USE`: what a `picture` operation did, in plain words (`context.PICTURE_USES`).
"""
from __future__ import annotations

import re

REMOVE = re.compile(r"\b(?:remove|delete|cut|drop|lose|scrap|ditch|erase|trim|shorten|shorter|fewer|less|without|"
                    r"strike|skip|axe|get\s+rid|no\s+more|no\s+longer|(?:take|leave|throw|pull)\b[^.!?]*?\b"
                    r"(?:out|away|off))\b", re.I)
_LEAD = re.compile(r"(?:(?:ok(?:ay)?|great|good|yes|yeah|so|well|alright|right|now|please|hub)\b[\s,.!]*)+", re.I)
_IT = r"(?:it|this|that|the\s+(?:script|story|scene|video|whole\s+thing)|everything)"
DONE = re.compile(rf"(?:(?:{_IT}|we|i)(?:['’]s|['’]re|['’]m|\s+is|\s+are|\s+am)\s+)?(?:all\s+)?(?:done|finished|"
                  r"complete|written)(?:\s+now)?(?:,?\s+thanks?(?:\s+you)?)?\s*[.!]*|that['’]?s\s+it\s*[.!]*", re.I)
VAGUE = ("tell me what to change in your own words: who says what, what a shot shows, who wears what, or how long "
         "it runs; or say render")
NO_STORY = "Tell me the story in your own words and the Hub writes the script."
EVERY = "said every scene done"
ALREADY = "every scene was done already"
USE = {"reference": "{}'s picture is the reference in every shot", "frame": "{}'s picture is the first frame",
       "none": "{} is made from the words, not the picture"}


def _bare(text: str) -> str:
    rest = text.strip()
    if (m := _LEAD.match(rest)) is not None:
        rest = rest[m.end():]
    return rest.strip()


def asks_removal(text: str) -> bool:
    return REMOVE.search(text) is not None


def done(text: str) -> bool:
    return DONE.fullmatch(_bare(text)) is not None


def removals(ops: list[dict], text: str) -> tuple[list[str], set[int]]:
    """Each removal blamed when `text` asks for none (1-based, as `saycheck`'s lines)."""
    if asks_removal(text):
        return [], set()
    bad = {k for k, op in enumerate(ops, 1) if op.get("op") == "remove" or op.get("op") == "cast" and op.get("remove")}
    return [f"operation {k} ({ops[k - 1]['op']}) takes out what the message does not ask to take out"
            for k in sorted(bad)], bad


def lines(script: dict) -> int:
    return sum(1 for sc in script.get("scenes", []) for shot in sc.get("shots", []) for ev in shot.get("events", [])
               if ev.get("kind") == "line")


def lost(before: dict, after: dict, text: str) -> int:
    """The lines `after` has fewer than `before` when `text` does not ask to take any out; else 0."""
    n = lines(before) - lines(after)
    return n if n > 0 and not asks_removal(text) else 0


def lost_line(n: int) -> str:
    return (f"the operations take out {n} line{'' if n == 1 else 's'} the message does not ask to take out; keep each "
            "line the message does not name")
