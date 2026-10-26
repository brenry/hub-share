"""Held shots in plain messages , pure. The Hub never adds a shot and
never sets a shot's length; a story's shots and their seconds are the planner's (`saystory`).
- `wants_render`: the message asks to write the script and then render it (`RENDER_TOO`).
- `rendered`: the answer's part for that press; `sentence`: what is not finished, as one plain sentence (no tool, no
  fix, no count of words).
"""
from __future__ import annotations

import re
from typing import Any

RENDER_TOO = re.compile(r"\brender(?:s|ed|ing)?\b|\b(?:produce|generate|create|make|output|export)\s+(?:it|this|that|"
                        r"the\s+(?:video|clip|cut|movie|storyboard))\b", re.I)
_HEAD = re.compile(r"^\s*(?:not done:\s*)?(?:[^:]*\bis not done:\s*)?(?:\d+\s+gaps?:\s*)?", re.I)
_PAREN = re.compile(r"\s*\([^()]*\)")
_WORDS = re.compile(r"[,;:]?\s*(?:about\s+)?\d+\s+(?:more\s+)?words?\b[^.;]*", re.I)


def wants_render(text: str) -> bool:
    return RENDER_TOO.search(text) is not None


def rendered(got: dict) -> str:
    """The answer's part for Render pressed after the write (`render.press`'s answer)."""
    if "problem" in got:
        return sentence(f"the video did not start: {got['problem']}")
    n = int(got.get("shots") or 0)
    return f"rendering {n} shot{'' if n == 1 else 's'}"


def sentence(text: Any) -> str:
    """One plain sentence of what is not finished: no parenthesis, no `not done:`, no request for words."""
    t = _HEAD.sub("", str(text))
    t = _WORDS.sub("", _PAREN.sub("", t))
    t = re.sub(r"\s{2,}", " ", t).strip(" ,;:.")
    if len(t) > 160:
        t = t[:159].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return (t[:1].upper() + t[1:] + ("" if t.endswith("…") else ".")) if t else ""
