"""Where the tools place events, pure. Times stay absolute in the file. Shots lie end to
end in script order: a shot starts where the one before ends (the first at 0) and ends at its latest line's or cue's
end, or one second after its latest pose's start, at least `SHOT_MIN_MS` after its own start, and at least its own
held length when it holds one (`seconds`, above 0 and up to `HOLD_MAX_S`, whole or tenths; `hold_ms`); it
holds at most `SHOT_MAX_MS` (one Ref2VA pass, R48 §7). A line lasts its words at its pace plus the turn pause (R48 §3,
A.4's formula); a cue 2 s until changed; a pose holds until the same character's next pose in the shot, else the
shot's end; an anchored cue or pose starts at its line's start or end. Timing the script again after a change, the
pushes and the checks are `timing.py`; here is where a new event lands, the line's length and the refusal's
shape.
"""
from __future__ import annotations

import json
from typing import Any

from hub.core.api import Invalid, spoken_words

PACE = 2.6                       # words per second (R48 §3)
TURN_MS = 180                    # the turn pause (R48 §3)
SHOT_MIN_MS = 1_000
SHOT_MAX_MS = 15_080             # 362 frames at 24 fps (R48 §7)
CUE_MS = 2_000
POSE_MIN_MS = 1_000              # a pose is seen at least this long when nothing else holds the shot
LAST_POSE_MS = SHOT_MAX_MS - POSE_MIN_MS  # the latest pose start, its 1 s ending at the shot's own limit
AFTER_LINE_MS = 500              # a pose asked at a speaker's own line end is keyed this long after it
HOLD_MAX_S = 15.0                # a shot's held length, at most the model's one pass


def refuse(problem: str, fix: str, **hints: Any) -> Invalid:
    """A refusal: an `Invalid` whose text is the compact JSON `{problem, fix, hints}`."""
    return Invalid("script", json.dumps({"problem": problem, "fix": fix, "hints": hints}, separators=(",", ":"),
                                        ensure_ascii=False))


def secs(ms: int) -> str:
    return f"{ms / 1000:.2f}"


def secs_up(ms: int) -> str:
    """A time a fix asks a call to reach, rounded up to the next 10 ms (2 334 -> "2.34")."""
    return f"{-(-ms // 10) / 100:.2f}"


def line_ms(words: str, pace: float | None = None) -> int:
    """A line's length: words ÷ pace × 1000 + the turn pause, rounded (9 words at 2.6 -> 3642; the pace the line's
    own, else the Hub's, else the engine's 2.6)."""
    return round(spoken_words(words) / (pace or PACE) * 1000 + TURN_MS)


def max_words(room_ms: int, pace: float | None = None) -> int:
    """The most words a line can hold in `room_ms`."""
    return max(0, int((room_ms - TURN_MS) * (pace or PACE) / 1000))


def voice(script: dict, pace: float | None = None) -> dict[str, Any]:
    """A new line's voice field when none is sent: the Hub's pace to two decimals (`PACE`
    when none, or 0, is handed in). No language and no emotion that was not sent."""
    return {"pace": round(pace or PACE, 2)}


def held_seconds(value: Any) -> bool:
    """A shot's held length: a number above 0 and up to `HOLD_MAX_S` seconds, whole or tenths (the top is the
    engine's one pass, the bottom above 0)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return 0 < value <= HOLD_MAX_S and abs(value * 10 - round(value * 10)) < 1e-6


def action_ok(value: Any) -> bool:
    """A shot's action: text, not blank, of any length."""
    return isinstance(value, str) and bool(value.strip())


def action(value: Any) -> str | None:
    """A shot's action sent, checked, its spaces made single; None when none is sent."""
    if value is None:
        return None
    if not action_ok(value):
        raise refuse("A shot's action is text, not blank", "Send what we see happen in the shot")
    if str(value).lstrip().startswith("subject_definitions:"):     # a pasted H3 prompt: kept line for line
        return str(value).strip()
    return " ".join(str(value).split())


def hold_ms(shot: dict) -> int:
    """The shot's held length in ms; 0 for a shot that holds none."""
    value = shot.get("seconds")
    return round(value * 1000) if held_seconds(value) else 0


def shots(script: dict) -> list[dict]:
    return [shot for sc in script["scenes"] for shot in sc["shots"]]


def lines_of(shot: dict) -> list[dict]:
    return sorted((ev for ev in shot["events"] if ev["kind"] == "line"), key=lambda ev: (ev["start_ms"], ev["id"]))


def last_line_end(shot: dict) -> int:
    """Where a line or an unanchored cue goes: the end of the shot's last line, else the shot's start."""
    return max((ev["end_ms"] for ev in shot["events"] if ev["kind"] == "line"), default=shot["start_ms"])


def move(shot: dict, by: int) -> None:
    shot["start_ms"] += by
    shot["end_ms"] += by
    for ev in shot["events"]:
        ev["start_ms"] += by
        ev["end_ms"] += by


def new_shot(script: dict, scene: dict, after: dict | None, ident: str, camera: Any, seconds: Any = None) -> dict:
    """An empty shot of `SHOT_MIN_MS` (or its held `seconds`) after `after` (else at the scene's end), every
    later shot moved."""
    k = scene["shots"].index(after) + 1 if after is not None else len(scene["shots"])
    shot = {"id": ident, "start_ms": 0, "end_ms": SHOT_MIN_MS, "camera": camera, "events": []}
    if seconds is not None:
        shot["seconds"] = seconds
        shot["end_ms"] = max(SHOT_MIN_MS, hold_ms(shot))
    span = shot["end_ms"]
    scene["shots"].insert(k, shot)
    every = shots(script)
    n = next(i for i, s in enumerate(every) if s is shot)
    start = every[n - 1]["end_ms"] if n else 0
    move(shot, start)
    for later in every[n + 1:]:
        move(later, span)
    return shot
