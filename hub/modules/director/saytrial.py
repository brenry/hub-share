"""The trial of the operations, pure. `trial`: on a copy of the base, each operation's ordinary calls run as a
write runs them; a refused call goes first through the landing (`landing.mended`), taken when it keeps the message's
words and numbers (`keeps`), else its refusal's problem and facts are kept for the send-back, never its fix (the Hub
never adds a shot nor sets its seconds); then every touched scene said done (never refused). The Hub's line is
`sayline`'s. A member is cast with no picture (`context_set`'s `anyone`)."""
from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import Any

from hub.core.api import Invalid

from . import frame, landing, lock, panels, sayask, saycheck, scriptshape
from .sayline import CAP, cap, clause, follows, line, plain, refusal  # noqa: F401  (the line, read here)

NO_MODEL = "Set the Assistant's model in Settings"
Calls = list[tuple[str, dict]]


class Tried:
    """A trial: the calls accepted in order, the operations applied with their clauses, what was kept."""

    def __init__(self, script: dict, new: bool = False) -> None:
        self.script, self.new = script, new
        self.calls: Calls = []
        self.applied: list[tuple[dict, str | None]] = []
        self.kept: list[str] = []
        self.said: list[str] = []                      # what was done that no operation says
        self.rendered: str | None = None               # the answer's part of Render pressed after
        self.title: Any = None


def _fn(tool: str, args: dict, names: list[str], pace: float) -> Callable[[dict, dict, Any], dict]:
    from . import tools  # late: tools reads `say`, which reads this module

    if tool == "context_set":
        return lambda s, c, chars: frame.context_set(s, args, chars, names, pace=pace, anyone=True)
    if tool in ("scene_add", "scene_change"):
        return lambda s, c, chars: getattr(frame, tool)(s, args, pace=pace)
    if tool == "shot_add":
        return lambda s, c, chars: frame.shot_add(s, c, args)
    return tools._edit(tool, args, pace)


def run(script: dict, ids: dict, calls: Calls, characters: Any, names: list[str], pace: float) -> None:
    """The calls in order on `script` as a write runs them (`landing.write`, then the file's check)."""
    for tool, args in calls:
        landing.write(script, ids, characters, _fn(tool, args, names, pace), pace)
        scriptshape.read(script, characters)


def _try(script: dict, ids: dict, calls: Calls, *rest: Any) -> tuple[Any, Any]:
    """-> (the script, its ids) after the calls, on copies; or (the index of the refused call, its refusal)."""
    s, c = copy.deepcopy(script), dict(ids)
    for i, call in enumerate(calls):
        try:
            run(s, c, [call], *rest)
        except Invalid as e:
            return i, e
    return s, c


def _field(call: tuple[str, dict], key: str) -> Any:
    return call[1].get(key, (call[1].get("fields") or {}).get(key))


def keeps(sent: tuple[str, dict], fixed: Calls, spans: list[str], lengths: list[float]) -> bool:
    """The landing's calls keep `spans` (no cut of words holding a span of them) and `lengths`."""
    for call in (c for c in fixed if c[0] == sent[0]):
        was = _field(sent, "words")
        if isinstance(was, str) and _field(call, "words") != was and any(s in was for s in spans):
            return False
        was = _field(sent, "seconds")
        if was is not None and _field(call, "seconds") != was and any(abs(float(was) - n) < 1e-6 for n in lengths):
            return False
    return True


def _mend(script: dict, ids: dict, calls: Calls, i: int, e: Invalid, own: tuple[list[str], list[float]],
          *rest: Any) -> tuple[Calls, tuple[dict, dict]] | None:
    """The landing on the refused call `calls[i]`, taken when it keeps the message's words and numbers."""
    try:
        got = json.loads(e.text)
    except ValueError:
        return None
    before = _try(script, ids, calls[:i], *rest)
    if not isinstance(got, dict) or not isinstance(got.get("hints"), dict) or isinstance(before[0], int):
        return None
    characters, names, pace = rest
    attempt = landing.attempts(before[0], characters, before[1], pace, lambda t, a: _fn(t, a, names, pace))
    bare = copy.deepcopy(before[0])
    panels.strip(bare)
    fixed = landing.mended(*calls[i], got, bare, attempt)
    if fixed is None or not keeps(calls[i], fixed, *own):
        return None
    sent = [*calls[:i], *fixed, *calls[i + 1:]]
    done = _try(script, ids, sent, *rest)
    return None if isinstance(done[0], int) else (sent, done)


def trial(base: dict, counters: dict, pairs: list[tuple[int, dict]], words: str, new: bool, characters: Any,
          names: list[str], pace: float, samples: set[str], mend: bool = True) -> Tried:
    """On a copy of `base` (unlocked as a write would): each operation's calls, a refusal mended (not with `mend`
    False: a new story's shot list, written exactly or sent back) or kept; then
    every touched scene (every scene of a new story) said done; then, every scene done, the Director's lock gaps
    (the samples by stats, no panel states). Nothing written."""
    out, ids, rest = Tried(copy.deepcopy(base), new), dict(counters), (characters, names, pace)
    if lock.locked(out.script):
        lock.unlock(out.script)
    own = (saycheck.spans(words) + [t for t in [saycheck.to_text(words)] if t], saycheck.lengths(words))
    touched: set[int] = set()
    for k, op in pairs:
        try:
            calls, n = sayask.calls(op, out.script, ids)
        except Invalid as e:
            out.kept.append(f"operation {k}: {refusal(e)}")
            continue
        done = _try(out.script, ids, calls, *rest)
        if isinstance(done[0], int):
            found = _mend(out.script, ids, calls, done[0], done[1], own, *rest) if mend else None
            if found is None:
                out.kept.append(f"operation {k}: {refusal(done[1])}")
                continue
            calls, done = found
        out.applied.append((op, clause(op, calls, out.script, done[0])))
        out.script, ids = done
        out.calls += calls
        touched |= {n} if n else set()
    for n in range(1, len(out.script["scenes"]) + 1):
        if new or n in touched:
            call = ("scene_change", {"scene": n, "done": True})
            done = _try(out.script, ids, [call], *rest)
            if isinstance(done[0], int):
                out.kept.append(f"scene {n}: {refusal(done[1])}")
                continue
            out.script, ids = done
            out.calls.append(call)
    return out                                           # no lock checklist is sent back


def every(calls: list[tuple[str, dict]], names: list[str], pace: float) -> Callable[[dict, dict, Any], dict]:
    """The write's change: every accepted call in order, through `landing.write`."""
    def change(s: dict, c: dict, chars: Any) -> dict:
        run(s, c, calls, chars, names, pace)
        return {"did": "the Hub's message", "shot": None}
    return change
