"""The voice's pace: words per second of heard sound, measured from every spoken line the Hub makes.

A finished line is one WAV in Sounds and the words typed for it (the job's summary). The heard span (`speech_span`:
first sound to last, by the engine's own quiet line) divided by the engine's word count is one reading; `speech_pace` is
the running average of the last `RUNS_MAX` readings, kept in this module's data (`ctx.doc("pace")`, a cache, never a
log: two numbers). It starts at the engine's 2.6 and goes to the turn grouping (`SpeechRequest.pace`) and,
later, Director's clip length. A reading outside 1.0–6.0 words per second, or from a span under 1 s, is
a wrong read and is not kept. The assistant sees it in the settings view as `speech_pace` (words per second) and
`speech_pace_runs`; `reset` puts it back to the engine's.
"""
from __future__ import annotations

from hub.core.api import Ctx, speech_span, spoken_words

DOC = "pace"
ENGINE = 2.6                     # upstream dialogue.py:23, H3_DIALOGUE_WORDS_PER_SECOND
LOW, HIGH = 1.0, 6.0
MIN_SPAN = 1.0
RUNS_MAX = 20
START = {"pace": ENGINE, "runs": 0}


def read(ctx: Ctx) -> dict:
    d = ctx.doc(DOC, START).get()
    pace, runs = d.get("pace"), d.get("runs")
    ok = isinstance(pace, (int, float)) and LOW <= pace <= HIGH and isinstance(runs, int) and runs >= 0
    return {"pace": float(pace), "runs": runs} if ok else dict(START)


def current(ctx: Ctx) -> float | None:
    """The measured pace for a request, None until one line has been measured (the engine's figure then)."""
    d = read(ctx)
    return d["pace"] if d["runs"] > 0 else None


def reading(path, words: int) -> float | None:
    """One line's words per heard second; None when it cannot be a right read."""
    if words <= 0:
        return None
    try:
        span = speech_span(path)
    except (OSError, ValueError):
        return None
    if span is None or span < MIN_SPAN:
        return None
    rate = words / span
    return rate if LOW <= rate <= HIGH else None


def learn(ctx: Ctx, path, text: str) -> float | None:
    """Fold one finished line into the running average; the reading, or None when it was not kept."""
    return learn_rate(ctx, reading(path, spoken_words(text)))


def learn_rate(ctx: Ctx, rate: float | None) -> float | None:
    """Fold one reading (words per heard second; the words judge's span gives a sharper one) into the
    running average; the reading, or None when it was not kept (None, or outside the right range)."""
    if rate is None or not LOW <= rate <= HIGH:
        return None
    d = read(ctx)
    n = min(d["runs"], RUNS_MAX - 1)
    ctx.doc(DOC, START).replace({"pace": round((d["pace"] * n + rate) / (n + 1), 3), "runs": d["runs"] + 1})
    return rate


def reset(ctx: Ctx) -> None:
    ctx.doc(DOC, START).replace(dict(START))
