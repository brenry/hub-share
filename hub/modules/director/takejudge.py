"""A Track take's verdict (blueprint §12.2), pure: from the words judge's reading (`words`: heard,
first miss) and the worker's measurement (`measure`: speech boundaries, sound outside the words, loudness, true peak,
`hub/worker/adapters/takemeasure.py`) -> the core's `Take` (heard and extra speech re-take; a level only flags) and the
parts of the take's record (`measured`, `judge`). Every number read is passed through `finite` first: NaN and
Infinity become None before any comparison, so none is ever written. `TrackJudge` is the job's judge (core `Judge`).
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from hub.core.api import Take

PARAMS = {
    "dialogue_lufs": -23.0,        # EBU R 128 (2020): "normalised to a Target Level of -23.0 LUFS"
    "clip_dbtp": 0.0,              # full scale: a peak above it after the gain would clip
    "true_peak_dbtp": -1.0,        # EBU R 128: "shall not exceed -1 dBTP"; the programme's, held by 9b's limiter
    "level_tolerance_db": 10.0,    # the Hub's: past it the delivery, not a fader, is what is judged
    "cue_lufs": {                  # a cue's and the room's anchor; a listen first
        "effect": -27.0,           # an event between lines, 4 dB under the dialogue anchor
        "reaction": -27.0,         # the same: applause or laughter between lines
        "music": -33.0,            # a bed 10 dB under it: the engine mixer's own ducking depth (R42 §2, `depth_db` 10)
        "room": -45.0,             # heard only in the gaps, 22 dB under
    },
}                                  # the rulebook's from Step 13 (blueprint §11.2)
BLOCK_MS = 400                     # ebur128's momentary block: a shorter slice has no loudness
WHY_MAX = 300
NOT_HEARD = "not heard: the words judge did not run"
NOT_MEASURED = "not measured: no measurement came back"           # a cue's or the room's
SILENT = "silent"


def finite(x: Any) -> float | None:
    """A float when `x` is a finite number, else None (a bool is no number)."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return float(x) if math.isfinite(x) else None


def _whole(x: Any) -> int | None:
    value = finite(x)
    return None if value is None else round(value)


def _signed(x: float) -> str:
    return f"{x:+.1f}"


@dataclass(frozen=True)
class Verdict:
    take: Take
    measured: dict[str, Any] | None
    judge: dict[str, Any]


def verdict(words: Any, measure: Any, bars: Mapping[str, Any]) -> Verdict:
    """Heard, extra speech, level, in that order; `bars`: `words_bar`, `unscripted_s` (Generate's)."""
    p, whys = PARAMS, []
    heard_of = words if isinstance(words, dict) else {}
    heard, miss = finite(heard_of.get("heard")), finite(heard_of.get("first_miss"))
    judged = heard is not None
    heard_ok = not judged or heard >= float(bars["words_bar"])
    if not heard_ok:
        whys.append(f"heard {round(heard * 100)} %" + (f", first miss at {miss:.1f} s" if miss is not None else ""))
    got = measure if isinstance(measure, dict) else {"problem": "no measurement came back"}
    problem = got.get("problem")
    extra = None if problem is not None else finite(got.get("extra_s"))
    extra_ok = extra is None or extra <= float(bars["unscripted_s"])
    if not extra_ok:
        whys.append(f"{extra:.1f} s of sound outside the words")
    level, measured, gain = [], None, 0.0
    if problem is not None:
        level.append(f"not measured: {problem}")
    else:
        start, end = _whole(got.get("speech_start_ms")), _whole(got.get("speech_end_ms"))
        lufs, peak = finite(got.get("lufs")), finite(got.get("true_peak_dbtp"))
        if lufs is None:
            span = (end - start) if start is not None and end is not None else 0
            level.append(SILENT if span >= BLOCK_MS else "level: too short to measure")
        else:
            gain = round(p["dialogue_lufs"] - lufs, 1)
            if abs(lufs - p["dialogue_lufs"]) > p["level_tolerance_db"]:
                level.append(f"level: {lufs:.1f} LUFS")
            if peak is not None and peak + gain > p["clip_dbtp"]:
                level.append(f"level: peaks at {_signed(peak + gain)} dBTP after {_signed(gain)} dB")
        measured = {"speech_start_ms": start, "speech_end_ms": end, "length_ms": _whole(got.get("length_ms")),
                    "lufs": None if lufs is None else round(lufs, 1),
                    "true_peak_dbtp": None if peak is None else round(peak, 1), "gain_db": gain}
    whys += level
    passes = heard_ok and extra_ok
    ok = passes and judged and not level
    said = list(whys) if judged else [*whys, NOT_HEARD]
    if ok or not said:
        parts = [f"heard {round((heard or 0) * 100)} %"]
        if measured is not None and measured["lufs"] is not None:
            parts += [f"{measured['lufs']:.1f} LUFS", f"gain {_signed(gain)} dB"]
        line = " · ".join(parts)
    else:
        line = "; ".join(said)
    rank = (1.0 if passes else 0.0, heard or 0.0, -(extra or 0.0), 0.0 if level else 1.0)
    record = {"heard": None if heard is None else min(1.0, max(0.0, heard)),
              "first_miss_ms": None if miss is None else max(0, round(miss * 1000)),
              "extra_speech": None if extra is None else max(0.0, extra),
              "verdict": "ok" if ok else "flagged", "why": None if ok else "; ".join(said)[:WHY_MAX]}
    return Verdict(Take(passes, rank, line), measured, record)


def cue_verdict(measure: Any, kind: str) -> Verdict:
    """A cue's or the room's take, boundaries and level only: the gain to its kind's anchor; flagged when
    not measured, too short or silent, or clipping after the gain; a far-off level is only a gain. Never re-taken."""
    p, why = PARAMS, None
    got = measure if isinstance(measure, dict) else {"problem": NOT_MEASURED.removeprefix("not measured: ")}
    measured, gain = None, 0.0
    if got.get("problem") is not None:
        why = f"not measured: {got['problem']}"
    else:
        lufs, peak = finite(got.get("lufs")), finite(got.get("true_peak_dbtp"))
        if lufs is None:
            why = "level: too short or silent to measure"
        else:
            gain = round(p["cue_lufs"][kind] - lufs, 1)
            if peak is not None and peak + gain > p["clip_dbtp"]:
                why = f"level: peaks at {_signed(peak + gain)} dBTP after {_signed(gain)} dB"
        measured = {"speech_start_ms": _whole(got.get("speech_start_ms")),
                    "speech_end_ms": _whole(got.get("speech_end_ms")), "length_ms": _whole(got.get("length_ms")),
                    "lufs": None if lufs is None else round(lufs, 1),
                    "true_peak_dbtp": None if peak is None else round(peak, 1), "gain_db": gain}
        if kind == "reaction":
            decay = _whole(got.get("decay_ms"))
            measured["decay_ms"] = None if decay is None else max(0, decay)
    line = why or f"{measured['lufs']:.1f} LUFS · gain {_signed(gain)} dB"
    record = {"heard": None, "first_miss_ms": None, "extra_speech": None, "verdict": "flagged" if why else "ok",
              "why": None if why is None else why[:WHY_MAX]}
    return Verdict(Take(True, (1.0, 0.0 if why else 1.0), line), measured, record)


class TrackJudge:
    """The Track job's judge: `done` keeps each take's verdict by its task (a take is one task); `again(shot, t)`
    lets take t of a line run up to `takes_max` (a take runs again only when the one before did not pass).
    `kinds` {group (1-based): cue kind or "room"} marks a cue's or the room's one-take group, judged by
    `cue_verdict` and never taken again. `alone`, so a failed take never ends the job (the core's
    `jobgraph.absorbs`): each line, cue and the room fails alone."""

    alone = True

    def __init__(self, takes_of: tuple, bars: Mapping[str, Any], kinds: Mapping[int, str] | None = None) -> None:
        self.takes_of, self.bars, self.kinds = takes_of, dict(bars), dict(kinds or {})
        self.group = {take[0]: g for g, takes in enumerate(takes_of, 1) for take in takes} if kinds else {}
        self.seen: dict[int, Take] = {}
        self.records: dict[int, Verdict] = {}

    def done(self, task: int, d: Mapping[str, Any]) -> Take | None:
        if d.get("ok") is False:
            return None                                  # a failed task: the core's own verdict
        held = d.get("judge") if isinstance(d.get("judge"), dict) else {}
        kind = self.kinds.get(self.group.get(task, 0))
        found = verdict(held.get("words"), held.get("measure"), self.bars) if kind is None else cue_verdict(
            held.get("measure"), kind)
        self.seen[task], self.records[task] = found.take, found
        return found.take

    def again(self, shot: int, take: int) -> bool:
        return shot not in self.kinds and take <= int(self.bars["takes_max"])
