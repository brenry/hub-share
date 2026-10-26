"""The lock: the Hub's record of a Track press, pure. `lock` mends each line's voice
fields (`mend`, the pace alone) and writes `{locked: true, at}`, nothing checked; `unlock`
clears the record and the measured times. No write is refused "locked".
"""
from __future__ import annotations

import json
import math
from typing import Any

from hub.core.api import Invalid

from . import layout

MIN_SAMPLE_S = 2.0                     # R48 §5, "each at least 2 s"
FIELDS = ("pace",)                     # a line's language and emotion only when given


def locked(script: dict) -> bool:
    return bool(script.get("lock", {}).get("locked"))


def mend(script: dict, pace: float) -> int:
    """Each line missing its pace given the Hub's (`layout.voice`) -> the lines mended."""
    held, n = layout.voice(script, pace), 0
    for ev in (ev for shot in layout.shots(script) for ev in shot["events"] if ev["kind"] == "line"):
        if any(k not in ev for k in FIELDS):
            ev.update({k: held[k] for k in FIELDS if k not in ev})
            n += 1
    return n


def cut(seconds: float) -> str:
    """Seconds to two decimals, cut, never rounded up (1.999 -> 1.99)."""
    return f"{math.floor(seconds * 100 + 1e-9) / 100:.2f}"


def _problem(e: Invalid) -> str:
    try:
        got = json.loads(e.text)
    except ValueError:
        return e.text
    return str(got.get("problem", e.text)) if isinstance(got, dict) else e.text


def lock(script: dict, pace: float, at: str) -> dict[str, Any]:
    """The lines' voice fields mended, then the press recorded at `at` -> `{did, shot, mended}`."""
    mended = mend(script, pace)
    script["lock"] = {"locked": True, "at": at}
    return {"did": "locked", "shot": None, "mended": mended}


def unlock(script: dict) -> dict[str, Any]:
    script["lock"] = {"locked": False, "at": None}
    for shot in layout.shots(script):                  # unlocked, the plan is the only time
        shot.pop("measured", None)
        for ev in shot["events"]:
            ev.pop("measured", None)
    return {"did": "unlocked", "shot": None}
