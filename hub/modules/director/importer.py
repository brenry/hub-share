"""A pasted MiniMax H3 prompt made into shots: its six labelled fields read as written; its
`detailed_description` split at each time range (`0:00-0:03`, `00:03–00:05`, ...), one shot per range, held for the
range's length. Each shot's action is the prompt with every other field exactly as pasted and its description that
range's text alone, its time range restarted at 0:00 (one shot is one clip). Nothing is invented: a prompt with no
time range, or a range of 0 s or more than 15 s, is refused in one line and nothing is added."""
from __future__ import annotations

import re

from hub.core.api import Invalid

from . import layout

FIELDS = ("subject_definitions", "summary", "retention_analysis", "detailed_description", "overall_soundscape",
          "non_diegetic_music")
_FIELD = re.compile(r"^\s*(" + "|".join(FIELDS) + r")\s*:", re.M)
_TIME = r"(\d{1,2}):(\d{2}(?:\.\d+)?)"
_RANGE = re.compile(_TIME + r"\s*[-–—]\s*" + _TIME)
_SHOT = re.compile(r"\[Shot\s*\d+\]\s*")


def fields(text: str) -> dict[str, str]:
    """Each labelled field's text as pasted, in order; a prompt without `subject_definitions:` is refused."""
    marks = list(_FIELD.finditer(text))
    if not marks or marks[0].group(1) != "subject_definitions":
        raise Invalid("text", "A MiniMax H3 prompt starts with subject_definitions:")
    return {m.group(1): text[m.end():(marks[k + 1].start() if k + 1 < len(marks) else len(text))].strip()
            for k, m in enumerate(marks)}


def _secs(minutes: str, seconds: str) -> float:
    return int(minutes) * 60 + float(seconds)


def _stamp(seconds: float) -> str:
    whole = int(seconds)
    rest = round(seconds - whole, 2)
    return f"0:{whole:02d}" + (f"{rest:.2f}"[1:].rstrip("0").rstrip(".") if rest else "")


def shots(text: str) -> list[tuple[float, str]]:
    """(seconds, prompt) per time range of the description, in order."""
    got = fields(text)
    desc = got.get("detailed_description", "")
    ranges = list(_RANGE.finditer(desc))
    if not ranges:
        raise Invalid("text", "The description has no time range (like 0:00-0:03) to make shots from")
    marked = bool(_SHOT.search(desc))
    out = []
    for k, m in enumerate(ranges):
        start, end = _secs(m.group(1), m.group(2)), _secs(m.group(3), m.group(4))
        length = round(end - start, 1)
        if not 0 < length <= layout.HOLD_MAX_S:
            raise Invalid("text", f"The range {m.group(0)} lasts {length:g} s; a shot holds up to "
                          f"{layout.HOLD_MAX_S:g} s")
        said = _SHOT.sub("", desc[m.end():(ranges[k + 1].start() if k + 1 < len(ranges) else len(desc))]).strip()
        part = ("[Shot 1] " if marked else "") + f"{_stamp(0)}-{_stamp(length)} {said}".strip()
        prompt = "\n".join(f"{f}: {part if f == 'detailed_description' else got[f]}" for f in FIELDS if f in got)
        out.append((length, prompt))
    return out
