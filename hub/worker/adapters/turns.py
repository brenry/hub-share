"""A spoken line as the engine's turns: whole sentences grouped so that each group's planned length stays
at or under a target, each group one `Speaker 1:` block. Stdlib only.

The engine plans a turn at `words / 2.6 + 0.18 per [.!?;:] + 1.4` s, held between 4 and 45 s, its words counted
from the turn's text with every `[ ]` taken out (the speech model's upstream `dialogue.py:17-23`, `:129`, `:148-151`,
`:220-222`). `planned` mirrors that without the hold. A sentence ends at `.`, `!` or `?` (an ellipsis is one end)
followed by white space, not after a title or `vs`/`etc`; a number like `3.5` has no white space and never splits.
A sentence longer than the target is a block of its own (never cut inside); a last group under the engine's 4 s
floor joins the one before. The text's leading `[ ]` is taken off first and returned apart.
"""
from __future__ import annotations

import re
import unicodedata

# The engine names this module reads: none. The numbers below mirror upstream dialogue.py (cited above).
READS: dict[str, dict[str, str]] = {c: {} for c in ("wgp", "api", "definition", "settings", "generate_video",
                                                    "suffixes")}
WORDS_PER_SECOND = 2.6         # dialogue.py:23
STOP_SECONDS = 0.18            # per [.!?;:], dialogue.py:150
TURN_SECONDS = 1.4             # dialogue.py:151
FLOOR = 4.0                    # the least a turn is planned, dialogue.py:17

_DIRECTION = re.compile(r"\[([^\[\]\n]+)\]")       # dialogue.py:46
_LEAD = re.compile(r"^\s*((?:\[[^\[\]\n]+\]\s*)+)")
_END = re.compile(r"(?:\.{2,}|…|[.!?]+)[\"'”’)\]]*(?=\s)")
_KEEP = {"mr", "mrs", "ms", "dr", "st", "jr", "sr", "vs", "etc"}
_QUOTES = "\"'“”‘’ "


def words(text: str) -> int:
    """How many words the engine would count in a line (a voice's pace is these words over the seconds heard)."""
    return len(_words(text))


def _words(text: str) -> list[str]:
    """The engine's words of a turn: `[ ]` out, accents folded, letters and digits (dialogue.py:129, :220-222)."""
    spoken = re.sub(r"\s+", " ", _DIRECTION.sub(" ", text)).strip().strip(_QUOTES)
    folded = unicodedata.normalize("NFKD", spoken).encode("ascii", "ignore").decode().casefold()
    return re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", folded)


def planned(text: str, pace: float | None = None) -> float:
    """The engine's estimate of a turn's seconds, without its 4 to 45 s hold (dialogue.py:148-151); `pace` (words per
    second, the voice's measured pace) in place of the engine's 2.6 when given."""
    spoken = _DIRECTION.sub(" ", text)
    rate = pace if pace and pace > 0 else WORDS_PER_SECOND
    return len(_words(text)) / rate + len(re.findall(r"[.!?;:]", spoken)) * STOP_SECONDS + TURN_SECONDS


def sentences(text: str) -> tuple[str, list[str]]:
    """(the leading `[ ]` with its trailing space, or ""; the sentences of the rest, each stripped)."""
    lead = _LEAD.match(text or "")
    head = lead.group(1).strip() + " " if lead else ""
    rest = (text or "")[lead.end():] if lead else (text or "")
    out, start = [], 0
    for end in _END.finditer(rest):
        word = re.findall(r"[A-Za-z]+$", rest[start:end.start()])
        if end.group().startswith(".") and len(end.group().rstrip("\"'”’)]")) == 1 and word \
                and word[0].casefold() in _KEEP:
            continue
        out.append(rest[start:end.end()].strip())
        start = end.end()
    out.append(rest[start:].strip())
    return head, [s for s in out if s]


def blocks(text: str, target: float, pace: float | None = None) -> tuple[str, list[str]]:
    """(the leading `[ ]` as `sentences` gives it; whole sentences grouped greedily while a group's estimate (at
    `pace`) stays at or under `target`, a last group under the engine's floor joined to the one before)."""
    head, parts = sentences(text)
    groups: list[str] = []
    for part in parts:
        if groups and planned(f"{groups[-1]} {part}", pace) <= target:
            groups[-1] = f"{groups[-1]} {part}"
        else:
            groups.append(part)
    if len(groups) > 1 and planned(groups[-1], pace) < FLOOR:
        groups[-2:] = [f"{groups[-2]} {groups[-1]}"]
    return head, groups
