"""A message's operations checked before anything is applied (blueprint §21.3), pure: each check fails with
all its lines at once (at most `MOST`), each naming its operation, and the operations it blames (`bad`, 1-based) are
never written. Only the message's words are checked: the model's own words are never refused.
1. Fields: each operation has what its kind needs; a `ref` is one of the ref forms (`refs._form`).
2. The message's words verbatim: every span between double quotes (`"…"`, `“…”`) inside some operation's words,
   title, framing or move; in every message that is not a new story, the text after `to:` the words of a
   `change_line` / `change_cue` or inside a `change_shot`.
3. The message's numbers unchanged: each length written is an operation's `seconds`; a `seconds` not written is dropped
   from its operation, never refused, and an operation it leaves with nothing to do is not written;
   in a change, each thing it names with a number is an operation's ref of that form and number; in a story or an
   add, a count the message writes is the number of adds of that kind.
4. A change is never an add (`is_change`, read before `to:`): no `add_*` but `add_line` / `add_shot` beside a
   `set_length` (no range to refill a scene to), and at least one operation that is not an add.
5. A removal only when asked (`sayplain.removals`). A shot's `seconds` (`HELD`) is never dropped.
"""
from __future__ import annotations

import re
from typing import Any

from . import refs, sayplain

OPS = ("add_scene", "add_shot", "add_line", "add_cue", "add_pose", "change_line", "change_cue", "change_shot",
       "remove", "move", "set_length", "cast", "picture")                    # picture
ADDS, HELD = OPS[:5], ("add_shot", "change_shot")  # HELD's seconds; a new shot's set by the Director
NEEDS = {"add_scene": ("title",), "add_shot": ("seconds",), "add_line": ("speaker", "words"),
         "add_cue": ("cue", "words"), "add_pose": ("character", "pose"), "change_line": ("ref",),
         "change_cue": ("ref",), "remove": ("ref",), "move": ("ref",), "set_length": ("seconds",), "cast": ("name",),
         "picture": ("name", "picture_use")}
ONE_OF = {"change_line": ("words", "emotion"), "change_cue": ("words", "seconds"),
          "change_shot": ("framing", "on", "move", "seconds", "action"), "move": ("shot", "at")}
FORMS = {"change_line": ("speaker",), "change_cue": ("cue",), "change_shot": ("shot",), "remove": ("speaker", "cue",
         "shot"), "move": ("speaker", "cue")}
SAID_OP = {"add_scene": "a new scene", "add_shot": "a new shot", "add_line": "a new line", "add_cue": "a new cue",
           "add_pose": "a new pose", "change_line": "a line's change", "change_cue": "a cue's change", "change_shot":
           "a shot's change", "remove": "a removal", "move": "a move", "set_length": "a length", "cast": "a cast "
           "change", "picture": "a picture's use"}
SAID_FIELD = {"ref": "which one", "speaker": "who says it", "words": "its words", "emotion": "its feeling", "framing":
              "its framing", "on": "who it is on", "move": "its move", "title": "its title", "cue": "its kind",
              "character": "whose pose", "pose": "the pose", "seconds": "its length", "name": "a name", "shot": "its "
              "shot", "at": "where", "picture_use": "how the picture is used",
              "action": "what happens in it"}  # its words for each; an action holds them too
CHANGE = {"change", "make", "turn", "rewrite", "reword", "rephrase", "replace", "fix", "set", "shorten", "lengthen",
          "cut", "remove", "delete", "drop", "take", "move", "swap", "put", "use", "dress", "don", "stop"}
ADD = {"add", "more", "another", "extra", "also", "insert", "include", "continue"}
_UNITS = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
WORDS = {w: k for k, w in enumerate([*_UNITS, "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
                                     "sixteen", "seventeen", "eighteen", "nineteen"], 1)}
WORDS.update({"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60})
WORDS.update({f"{t}{sep}{u}": WORDS[t] + k for t in ("twenty", "thirty", "forty", "fifty") for k, u in
              enumerate(_UNITS, 1) for sep in ("-", " ")})
ORDINALS = {w: k for k, w in enumerate(("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth",
                                        "ninth", "tenth", "eleventh", "twelfth"), 1)}
_NUM = "|".join(sorted(map(re.escape, WORDS), key=len, reverse=True))
_ORD = "|".join(ORDINALS) + r"|\d+(?:st|nd|rd|th)|last"
_TIMES = "seconds?|secs?|s|minutes?"
_UNIT = rf"(?:{_TIMES})\b"
LENGTH = re.compile(rf"\b(half a|a|{_NUM}|\d+(?:\.\d+)?)\s*-?\s*({_TIMES})\b", re.I)
SPAN = re.compile(r'"([^"\n]+)"|“([^”\n]+)”')
TO = re.compile(r"\bto:\s*(.+)$", re.I | re.S)
BEFORE_TO = re.compile(r"\bto:", re.I)
LINE_REF = re.compile(rf"\b([^\W\d_][\w-]*)['’]s\s+({_ORD})\s+line\b", re.I)
CUE_REF = re.compile(rf"\bthe\s+({_ORD})\s+(reaction|music|effect)\s+cue\b", re.I)
NUMBERED = re.compile(rf"\b(shot|scene)\s+(\d+|{_NUM})\b(?!\s*-?\s*{_UNIT})", re.I)
COUNT = re.compile(rf"\b(\d+|{_NUM}|a single)\s+(scene|shot|line|cue)s?\b", re.I)
LEAD = re.compile(r"(?:please|now|ok|okay|so|(?:can|could|would)\s+you)\b[\s,.!]*", re.I)
NAME = re.compile(r"([^\W\d_][\w'-]*)\s*,\s*")


def _number(word: str) -> float:
    w = word.casefold()
    return 1 if w in ("a", "a single") else 0.5 if w == "half a" else WORDS.get(w) or float(w)


def lengths(text: str) -> list[float]:
    """Every length `text` writes, in seconds (`a minute` 60, `half a minute` 30; `a second` is no length)."""
    out = []
    for word, unit in LENGTH.findall(text):
        minutes = unit.casefold().startswith("minute")
        if word.casefold() in ("a", "half a") and not minutes:
            continue
        out.append(_number(word) * (60 if minutes else 1))
    return out


def spans(text: str) -> list[str]:
    return [a or b for a, b in SPAN.findall(text)]


def to_text(text: str) -> str | None:
    """The text after `to:` to the message's end, one pair of outer quotes off; None without one."""
    found = TO.search(text)
    if found is None:
        return None
    said = found.group(1).strip()
    for o, c in (('"', '"'), ("“", "”")):
        if len(said) >= 2 and said.startswith(o) and said.endswith(c):
            said = said[1:-1].strip()
            break
    return said or None


def is_change(text: str) -> bool:
    """Check 4 on the text before the first `to:` (the new words are never a signal): the first word (after
    `please`, `now`, `ok`, … and a name with a comma) a change verb, and no add word."""
    head = text[:found.start()] if (found := BEFORE_TO.search(text)) else text
    if any(w.casefold() in ADD for w in re.findall(r"[^\W\d_]+", head)):
        return False
    rest = head.lstrip()
    while (m := LEAD.match(rest) or NAME.match(rest)) is not None:
        if m.re is NAME and m.group(1).casefold() in CHANGE:
            break
        rest = rest[m.end():]
    first = re.match(r"[^\W\d_]+", rest)
    return first is not None and first.group(0).casefold() in CHANGE


def _ordinal(word: str) -> int | None:
    return None if (w := word.casefold()) == "last" else ORDINALS.get(w) or int(re.sub(r"\D", "", w))


def _texts(op: dict) -> list[str]:
    return [op[k] for k in ("words", "title", "framing", "move", "action") if isinstance(op.get(k), str)]


def _overlap(a: str, b: str) -> float:
    x, y = set(re.findall(r"\w+", a.casefold())), set(re.findall(r"\w+", b.casefold()))
    return len(x & y) / len(x) if x else 0.0


def _cut(text: str, n: int = 80) -> str:
    return text if len(text) <= n else text[:n].rstrip() + "…"


class Found:
    """The lines and the blamed operations of one check."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.bad: set[int] = set()

    def add(self, line: str, *bad: int) -> None:
        self.lines.append(line)
        self.bad.update(bad)


def fields(ops: list[dict], new: bool, title: Any) -> Found:
    """Check 1."""
    out = Found()
    if new and not (isinstance(title, str) and title.strip()):
        out.add("a new script needs its title")
    for k, op in enumerate(ops, 1):
        kind = op.get("op")
        missing = [f for f in NEEDS.get(kind, ()) if op.get(f) in (None, "", [])]
        if kind in ONE_OF and not any(op.get(f) not in (None, "", []) for f in ONE_OF[kind]):
            missing.append(" or ".join(ONE_OF[kind]))
        if kind == "change_shot" and "ref" not in op and "shot" not in op:
            missing.append("ref {shot}")
        if missing:
            out.add(f"operation {k} ({kind}) needs {', '.join(missing)}", k)
        elif "ref" in op and kind in FORMS and refs._form(op["ref"]) not in FORMS[kind]:
            out.add(f"operation {k} ({kind}) has a ref that is none of " + ", ".join(
                {"speaker": "{speaker, nth}", "cue": "{cue, nth}", "shot": "{shot: n}"}[f] for f in FORMS[kind]), k)
    return out


def verbatim(ops: list[dict], text: str, told: bool) -> Found:
    """Check 2; `told`: the to: check runs (every message that is not a new story)."""
    out = Found()
    for span in spans(text):
        if any(span in t for op in ops for t in _texts(op)):
            continue
        near = max(((k, t) for k, op in enumerate(ops, 1) for t in _texts(op)), key=lambda p: _overlap(span, p[1]),
                   default=None)
        if near is not None and _overlap(span, near[1]) >= 0.5:
            out.add(f'the message writes "{span}"; no operation holds it as written (operation {near[0]} has '
                    f'"{_cut(near[1])}")', near[0])
        else:
            out.add(f'the message writes "{span}"; no operation holds it as written')
    said = to_text(text) if told else None
    if said is None:
        return out
    held = [k for k, op in enumerate(ops, 1) if op.get("op") in ("change_line", "change_cue") and
            op.get("words") == said or op.get("op") == "change_shot" and
            any(said in str(op.get(f, "")) for f in ("framing", "move", "action"))]
    if not held:
        near = [k for k, op in enumerate(ops, 1) if op.get("op") in ("change_line", "change_cue") and
                isinstance(op.get("words"), str)]                  # the paraphrases of the message's words, blamed
        has = f' (operation {near[0]} has "{_cut(ops[near[0] - 1]["words"])}")' if near else ""
        out.add(f'the message writes "{said}"; no operation holds it as written{has}', *near)
    for k, op in enumerate(ops, 1):
        if op.get("op") in ADDS and any(said in t for t in _texts(op)):
            out.add(f'the message asks to change something to "{_cut(said)}"; operation {k} adds it', k)
    return out


def _seconds(op: dict) -> float | None:
    v = op.get("seconds")
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _lines_of(script: dict, who: str, scene: Any) -> int:
    n = scene if isinstance(scene, int) and 1 <= scene <= len(script.get("scenes", [])) else len(
        script.get("scenes", []))
    if not n:
        return 0
    return sum(1 for _, ev in refs._numbered(script["scenes"][n - 1], "line")
               if str(ev.get("speaker", "")).casefold() == who.casefold())


def _names_line(op: dict, who: str, k: int | None, script: dict) -> bool:
    for ref in (op.get("ref"), op.get("at")):
        if isinstance(ref, dict) and str(ref.get("speaker", "")).casefold() == who.casefold():
            want = k if k is not None else _lines_of(script, who, ref.get("scene", op.get("scene")))
            if ref.get("nth") == want or k is None and not want:
                return True
    return False


def numbers(ops: list[dict], text: str, change: bool, script: dict) -> Found:
    """Check 3."""
    out = Found()
    wrote, set_ = lengths(text), [(k, v) for k, op in enumerate(ops, 1) if (v := _seconds(op)) is not None and
                                  op.get("op") not in HELD]          # a shot's hold is the planner's own
    left = [n for n in wrote if not any(abs(v - n) < 1e-6 for op in ops if (v := _seconds(op)) is not None)]
    extra = [(k, v) for k, v in set_ if not any(abs(v - n) < 1e-6 for n in wrote)]
    for n, (k, v) in zip(left, extra, strict=False):
        out.add(f"the message writes {n:g} seconds; operation {k} says {v:g}", k)
    for n in left[len(extra):]:
        out.add(f"the message writes {n:g} seconds; no operation sets it")
    for k, _ in extra[len(left):]:                       # a length the message does not name is dropped
        op = ops[k - 1]
        op.pop("seconds", None)
        if op.get("op") == "set_length" or op.get("op") == "change_cue" and not op.get("words"):
            out.bad.add(k)                               # nothing left to do: not written, no line
    if change:
        for who, word in LINE_REF.findall(text):
            k = _ordinal(word)
            if not any(_names_line(op, who, k, script) for op in ops):
                near = [j for j, op in enumerate(ops, 1) if isinstance(op.get("ref"), dict) and
                        str(op["ref"].get("speaker", "")).casefold() == who.casefold()]
                says = f"operation {near[0]} says {who}'s {refs.ordinal(ops[near[0] - 1]['ref'].get('nth', 0))} " \
                    "line" if near else "no operation names it"
                out.add(f"the message names {who}'s {word} line; {says}", *near[:1])
        for word, cue in CUE_REF.findall(text):
            k = _ordinal(word)
            if not any(isinstance(r := op.get("ref"), dict) and r.get("cue") == cue.casefold() and
                       (k is None or r.get("nth") == k) for op in ops):
                out.add(f"the message names the {word} {cue} cue; no operation names it")
        for what, word in NUMBERED.findall(text):
            n, key = int(_number(word)), what.casefold()
            if not any(op.get(key) == n or isinstance(op.get("ref"), dict) and op["ref"].get(key) == n
                       for op in ops):
                out.add(f"the message names {key} {n}; no operation names {key} {n}")
        return out
    for word, kind in COUNT.findall(text):
        n, made = int(_number(word)), sum(1 for op in ops if op.get("op") == f"add_{kind.casefold()}")
        if n != made:
            out.add(f"the message writes {word} {kind.casefold()}{'' if n == 1 else 's'}; the operations add {made}")
    return out


def adds(ops: list[dict], text: str, script: dict) -> Found:
    """Check 4, for a change message (no range around a named length, so no scene is refilled)."""
    out = Found()
    length = any(op.get("op") == "set_length" for op in ops)
    named = NUMBERED.search(text) or LINE_REF.search(text)
    what = f" ({'change_shot' if named and named.re is NUMBERED else 'change_line'} {named.group(0)})" if named \
        else ""
    for k, op in enumerate(ops, 1):
        if op.get("op") in ADDS and not (length and op.get("op") in ("add_line", "add_shot")):
            out.add(f"the message asks for a change; change what it names{what}, never add one (operation {k} is "
                    f"{op.get('op')})", k)
    if ops and all(op.get("op") in ADDS for op in ops) and not out.lines:
        out.add("the message asks for a change; the operations only add")
    return out


def check(value: dict, text: str, script: dict, new: bool) -> tuple[list[dict], list[str], set[int]]:
    """The checks on the reply `value` ({title?, operations}) for the chat message `text`, `script` the base as read:
    -> (the operations, every line, the blamed operations)."""
    ops = [op for op in value.get("operations", []) if isinstance(op, dict)]
    change = not new and is_change(text)
    found = [fields(ops, new, value.get("title")), verbatim(ops, text, not new), numbers(ops, text, change, script)]
    if change:
        found.append(adds(ops, text, script))
    found.append(Found())
    found[-1].lines, found[-1].bad = sayplain.removals(ops, text)
    lines = [line for f in found for line in f.lines]
    return ops, lines, set().union(*(f.bad for f in found))
