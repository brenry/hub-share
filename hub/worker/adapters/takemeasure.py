"""A spoken take measured on arrival, in the worker, without a model ask (blueprint §12.2): where its
speech starts and ends inside the file, the sound outside it, and the speech's integrated loudness and true peak.
Stdlib only; every number comes from the engine's ffmpeg (`soundtail.ffmpeg()`), nothing is written (`-f null -`).

The sound regions are the file less ffmpeg's `silencedetect` silences (-45 dB for 0.15 s keep the pauses between
words inside one region and split a cough off by its silence). The words judge's first and last matched word
(`judge.score` `first`, `last`, seconds) are snapped to the region that holds each, never more than 0.30 s before the
first word (a garble glued to it is cut) nor 0.50 s after the last (its decay kept). The loudness is ffmpeg's
`ebur128=peak=true` over that slice, run at `-v info` (ffmpeg prints the `Summary:` block only at info or verbose),
read after `Summary:` only (its 100 ms lines hold `I:` too): the Summary's `I:` (LUFS) and, under `True peak:`,
`Peak:` (dBFS); a slice under 400 ms, in the whole milliseconds the record writes, is measured over the whole take
instead. A number that is not finite (a silent take's `Peak: -inf`), an `I:` at or below -70 (ebur128's absolute
gate) or a slice under 400 ms (its momentary block) is None: nothing here returns NaN or Infinity.

A cue or the room is measured without words (the first region's start, the last one's end). With `decay`
(a reaction cue) the same `ebur128` run is at `-v verbose`, which prints a line every 100 ms, `t: <s> … M:<LUFS>`
(the momentary loudness of the 400 ms ending at `t`, in the file's own time); `decay_ms` is the kept end less the
last `t` whose `M` is within `DECAY_DB` of the loudest `M`, whole, at least 0 (None when no `M` is above the gate).
"""
from __future__ import annotations

import math
import re
import subprocess
from collections.abc import Callable, Sequence
from typing import Any

from . import soundtail

# The engine names this module reads: none (it runs ffmpeg, as `soundtail` finds it, on the take's file).
READS: dict[str, dict[str, str]] = {c: {} for c in ("wgp", "api", "definition", "settings", "generate_video",
                                                    "suffixes")}
NO_FFMPEG = "ffmpeg is not installed on the server"     # the words of `hub/worker/join.py`'s NO_FFMPEG
NO_LENGTH = "the take does not decode"
SECONDS = 60                    # the most one ffmpeg run may take
NOISE, QUIET = "-45dB", 0.15    # silencedetect: the floor and the shortest silence
BEFORE, AFTER = 0.30, 0.50      # the most kept before the first word and after the last
GATE = -70.0                    # ebur128's absolute gate: an `I:` at or below it is no loudness
BLOCK = 0.4                     # ebur128's momentary block: a shorter slice has no loudness
BLOCK_MS = 400                  # the same, in the whole milliseconds the record writes
DECAY_DB = 10.0                 # the decay starts at the last moment within this of the loudest
_START = re.compile(r"silence_start:\s*(-?[0-9.]+(?:e-?\d+)?)")
_END = re.compile(r"silence_end:\s*(-?[0-9.]+(?:e-?\d+)?)")
_I = re.compile(r"^\s*I:\s*(\S+)\s*LUFS", re.MULTILINE)
_PEAK = re.compile(r"True peak:\s*\n\s*Peak:\s*(\S+)\s*dBFS")
_MOMENT = re.compile(r"\bt:\s*([0-9.]+(?:e-?\d+)?)\s.*?\bM:\s*(\S+)")
Run = Callable[[list[str]], "str | None"]


def finite(value: Any) -> float | None:
    """A float when `value` is a finite number (text included), else None."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def silences(text: str, length: float) -> list[tuple[float, float]]:
    """ffmpeg's silences from its stderr, in order: a `silence_start` with no end runs to `length`; either may share a
    line with progress text."""
    out, start = [], None
    for line in text.splitlines():
        for found in _START.finditer(line):
            start = finite(found.group(1))
        for found in _END.finditer(line):
            end = finite(found.group(1))
            if start is not None and end is not None:
                out.append((max(0.0, start), min(length, end)))
            start = None
    if start is not None:
        out.append((max(0.0, start), length))
    return out


def regions(quiet: Sequence[tuple[float, float]], length: float) -> list[tuple[float, float]]:
    """`[0, length]` less the silences: the stretches that sound."""
    out, at = [], 0.0
    for start, end in sorted(quiet):
        if start > at:
            out.append((at, min(start, length)))
        at = max(at, end)
    if at < length:
        out.append((at, length))
    return [(a, b) for a, b in out if b > a]


def _holding(spans: Sequence[tuple[float, float]], t: float) -> tuple[float, float] | None:
    return next(((a, b) for a, b in spans if a <= t <= b), None)


def bounds(spans: Sequence[tuple[float, float]], length: float, first: Any, last: Any) -> tuple[float, float]:
    """The speech's start and end in seconds, clamped to `[0, length]`."""
    first, last = finite(first), finite(last)
    if first is not None and last is not None:
        held_in, held_out = _holding(spans, first), _holding(spans, last)
        start = max(held_in[0] if held_in else first, first - BEFORE)
        end = min(held_out[1] if held_out else last, last + AFTER)
    elif spans:
        start, end = spans[0][0], spans[-1][1]
    else:
        start, end = 0.0, length
    start, end = min(max(0.0, start), length), min(max(0.0, end), length)
    return start, max(start, end)


def outside(spans: Sequence[tuple[float, float]], start: float, end: float) -> float:
    """The sounding seconds outside `[start, end]`."""
    return float(sum(max(0.0, min(b, start) - a) + max(0.0, b - max(a, end)) for a, b in spans))


def loudness(text: str) -> tuple[float | None, float | None]:
    """The ebur128 Summary's integrated loudness (None at or below the gate) and true peak, each finite or None."""
    tail = text[text.rfind("Summary:"):] if "Summary:" in text else ""
    i, peak = _I.search(tail), _PEAK.search(tail)
    lufs = finite(i.group(1)) if i else None
    true_peak = finite(peak.group(1)) if peak else None
    return (round(lufs, 1) if lufs is not None and lufs > GATE else None,
            round(true_peak, 1) if true_peak is not None else None)


def decay_of(text: str, end: float) -> int | None:
    """The ms from the last momentary reading within `DECAY_DB` of the loudest to `end`; None with no reading."""
    body = text[:text.rfind("Summary:")] if "Summary:" in text else text
    moments = [(t, m) for line in body.splitlines() for found in _MOMENT.finditer(line)
               if (t := finite(found.group(1))) is not None and (m := finite(found.group(2))) is not None and m > GATE]
    if not moments:
        return None
    top = max(m for _, m in moments)
    last = max(t for t, m in moments if m >= top - DECAY_DB)
    return max(0, round((end - last) * 1000))


def _ffmpeg(program: str) -> Run:
    def run(args: list[str]) -> str | None:
        try:
            done = subprocess.run([program, "-nostdin", "-hide_banner", "-v", "info", *args], capture_output=True,
                                  timeout=SECONDS, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return done.stderr.decode("utf-8", "replace") if done.returncode == 0 else None
    return run


def measure(path: str, words: Any, run: Run | None = None,
            length: Callable[[str], float | None] | None = None, decay: bool = False) -> dict[str, Any]:
    """{length_ms, speech_start_ms, speech_end_ms, extra_s, lufs, true_peak_dbtp}, or {"problem": one line}.
    `words`: the words judge's verdict (its `first`, `last`), or None. `run`, `length`: stand-ins for a test.
    `decay`: `decay_ms` beside them."""
    if run is None:
        program = soundtail.ffmpeg()
        if program is None:
            return {"problem": NO_FFMPEG}
        run = _ffmpeg(program)
    seconds = finite((length or soundtail.sound_seconds)(path))
    if seconds is None or seconds <= 0:
        return {"problem": NO_LENGTH}
    found = run(["-i", path, "-af", f"silencedetect=noise={NOISE}:d={QUIET}", "-f", "null", "-"])
    spans = regions(silences(found or "", seconds), seconds) if found is not None else [(0.0, seconds)]
    heard = words if isinstance(words, dict) else {}
    start, end = bounds(spans, seconds, heard.get("first"), heard.get("last"))
    lufs = peak = level = None
    held = round(end * 1000) - round(start * 1000) >= BLOCK_MS          # the record's milliseconds
    over = f"atrim=start={start:.3f}:end={end:.3f}," if held else ""                  # short: the whole take
    if over or seconds >= BLOCK:
        verbose = ["-v", "verbose"] if decay else []                   # the later -v wins over `_ffmpeg`'s info
        level = run([*verbose, "-i", path, "-af", f"{over}ebur128=peak=true", "-f", "null", "-"])
        lufs, peak = loudness(level or "")
    out = {"length_ms": round(seconds * 1000), "speech_start_ms": round(start * 1000),
           "speech_end_ms": round(end * 1000), "extra_s": round(outside(spans, start, end), 2),
           "lufs": lufs, "true_peak_dbtp": peak}
    return {**out, "decay_ms": decay_of(level or "", end)} if decay else out
