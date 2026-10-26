"""The words judge: a spoken line's WAV is transcribed by the engine's own Whisper and scored against the
words it was given, before anyone listens. Stdlib only; the engine's modules are imported at the call, inside the
engine's Python.

Upstream `shared/deepy/transcription.py` `transcribe_media(path, timestamp_type="word", model_name="medium",
device=…)` returns `segments[].words[]` with `word`, `start`, `end`, `probability` (:211-275, :183-209). The speech
route's own trim loads the same medium model on CPU (its `dialogue.py:204-217`), so CPU is the engine's choice for
this model beside the speech model, and the judge's too. The heard words are aligned to the written ones with the
speech route's own aligner (match / substitution / insertion labels, a deletion leaving an expected word unlabelled)
over its own word normalisation; the module that holds both is named in the facts file (`speech.aligner`), never
here. A written word counts as heard when the alignment labels it a match. `READS` names nothing of the categories
the contract test walks: what this module reads is the transcription module cited above and the facts file's.

Whisper is loaded once per worker and kept: `transcribe_media` with no `prepared_model` loads the model
for that call and drops it (upstream :225-226, :257-259), so every take would pay a load. The judge loads it with the
engine's own loader (`LOADER`, the function `transcribe_media` calls; same files, dtype float32 and CPU) and hands it
over in a fresh one-item list each call, which the engine pops; the judge's own reference keeps it. The lane bounds
the worker's life (one job on a video model, or the speech model until it is unloaded), and the model goes with the
worker. A load that fails keeps nothing (the next take tries again); a transcription that fails keeps the model. An
engine without the loader is called with no `prepared_model`, a load per take. No lock: the worker runs one task at
a time.
"""
from __future__ import annotations

import importlib
from typing import Any

from . import turns

TRANSCRIPTION = "shared.deepy.transcription"
LOADER = "_load_whisper_medium"
READS: dict[str, dict[str, str]] = {c: {} for c in ("wgp", "api", "definition", "settings", "generate_video",
                                                    "suffixes")}


_kept: list[Any] = []                                         # one Whisper per worker, for the worker's life


def _whisper(transcription: Any) -> Any:
    """The kept model, loaded on the CPU by the engine's own loader when none is kept; None when the engine has no
    loader (then each take loads its own). A load that raises propagates and keeps nothing."""
    if not _kept:
        loader = getattr(transcription, LOADER, None)
        if loader is None:
            return None
        _kept.append(loader(transcription.torch.device("cpu")))
    return _kept[0]


def _heard(report: dict[str, Any], normalize: Any) -> list[tuple[str, float, float]]:
    """(word, start, end) for every heard word, in order, each in the engine's normalised form (a heard token that
    normalises to several words gives several, at the same time)."""
    out: list[tuple[str, float, float]] = []
    for segment in report.get("segments") or []:
        for w in (segment.get("words") or []) if isinstance(segment, dict) else []:
            start = w.get("start") if isinstance(w.get("start"), (int, float)) else 0.0
            end = w.get("end") if isinstance(w.get("end"), (int, float)) else start
            for token in normalize(str(w.get("word") or "")):
                out.append((token, float(start), float(end)))
    return out


def score(heard: list[tuple[str, float, float]], expected: list[str], align: Any) -> dict[str, Any]:
    """`heard` (the share of written words labelled a match, 0–1), `first_miss` (the second the first unheard written
    word should have come, by the heard word before it, or 0.0; None when all were heard), `span` (from the first
    heard word's start to the last heard word's end), `words` (how many were written); `first` and `last`: the
    first matched word's start and the last matched word's end, where the line sits in the file, None when no
    written word was heard."""
    if not expected:
        return {"heard": 0.0, "first_miss": None, "span": 0.0, "words": 0, "first": None, "last": None}
    labels = align([w for w, _, _ in heard], expected)
    matched: dict[int, int] = {}                                   # expected index -> heard index
    row = 0
    for label, column in labels:
        if label == "insertion":
            row += 1
            continue
        if label == "match" and column is not None:
            matched[column] = row
        if label in ("match", "substitution"):
            row += 1
    first_miss: float | None = None
    for index in range(len(expected)):
        if index in matched:
            continue
        before = [matched[i] for i in range(index) if i in matched]
        first_miss = heard[before[-1]][2] if before else 0.0
        break
    span = (heard[-1][2] - heard[0][1]) if heard else 0.0
    return {"heard": round(len(matched) / len(expected), 4),
            "first_miss": None if first_miss is None else round(first_miss, 2),
            "span": round(max(0.0, span), 3), "words": len(expected),
            "first": round(heard[min(matched.values())][1], 2) if matched else None,
            "last": round(heard[max(matched.values())][2], 2) if matched else None}


def words(path: str, text: str, language: str | None = None) -> dict[str, Any] | None:
    """The words judge on the WAV at `path` against `text` (the line as typed: its `[ ]` directions are not words).
    None when the engine cannot transcribe here (its files absent, an import that fails), never an exception."""
    from . import upstream  # late: the facts file names the aligner's module; upstream imports this through joins

    try:
        facts = upstream.facts_file()["speech"]["aligner"]
        transcription = importlib.import_module(TRANSCRIPTION)
        aligner = importlib.import_module(str(facts["module"]))
        model = _whisper(transcription)
        kept = {} if model is None else {"prepared_model": [model]}   # a fresh list: the engine pops it
        report = transcription.transcribe_media(path, timestamp_type="word", model_name="medium", device="cpu",
                                                language=language, **kept)
    except Exception:  # noqa: BLE001  (the judge is advice; a line that cannot be judged still lands)
        return None
    try:
        normalize, align = getattr(aligner, str(facts["normalize"])), getattr(aligner, str(facts["align"]))
        expected = turns._words(str(text or ""))              # the line's words, its `[ ]` out, the engine's form
        return score(_heard(report if isinstance(report, dict) else {}, normalize), expected, align)
    except Exception:  # noqa: BLE001
        return None
