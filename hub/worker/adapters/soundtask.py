"""A sound from a prompt alone: the engine task of a `SoundRequest`. Stdlib only.

The speech model the facts file marks `sounds` (`upstream.facts.json` `speech.sounds`, whose `why` cites the engine's
lines) renders a prompt that is not a `Speaker N:` script as one sound, skipping its dialogue path, at exactly
`duration_seconds`, which it takes from 4 to 300 s. No sample: `audio_prompt_type` is empty. The prompt is the
request's, as written. A cue's sound model (the facts file's `cues`, by kind, best first) takes the same
task (an empty `audio_prompt_type` is its text to audio); `cue_facts` is what the catalog marks it with, and a model
the facts file lists under `flash` is `blocked` when the engine's own Flash Attention 2 test fails (`flash_ready`),
run again at every catalog.
"""
from __future__ import annotations

import importlib
import importlib.util
from typing import Any

BLOCKED = "needs Flash Attention 2, not installed"


def seeded(request: Any) -> dict[str, Any]:
    """The task's `seed` when the request has one; {} when it is None, so the engine's own default applies (on
    upstream the model's factory seed, -1 a fresh draw, R55 §2.1)."""
    seed = getattr(request, "seed", None)
    return {} if seed is None else {"seed": seed}


def sound(request: Any, entry: dict) -> dict[str, Any]:
    """The task of one sound: the prompt, the seed and the length, one take."""
    return {"model_type": request.model, "prompt": request.prompt, **seeded(request), "batch_size": 1,
            "multi_prompts_gen_type": "FG", "duration_seconds": request.seconds, "audio_prompt_type": ""}


def cues(facts: dict, model_type: str) -> dict[str, int]:
    """{cue kind: the model's rank in that kind's list (0 best)} from the facts file's `cues`; {} when it has none."""
    table = facts.get("cues") if isinstance(facts, dict) else None
    if not isinstance(table, dict):
        return {}
    return {kind: ids.index(model_type) for kind, ids in table.items()
            if kind not in ("why", "flash") and isinstance(ids, list) and model_type in ids}


def flash_ready() -> bool:
    """The engine's own test of Flash Attention 2 (`upstream models/TTS/stable_audio3_handler.py:89-96`): the module
    is found, imports, and its `flash_attn_varlen_func` is callable; False on any error. No cache, the
    import system's finders cleared first, so a module installed since the worker started is found at the next
    catalog (every Rescan)."""
    try:
        importlib.invalidate_caches()
        if importlib.util.find_spec("flash_attn") is None:
            return False
        module = importlib.import_module("flash_attn")
        return callable(getattr(module, "flash_attn_varlen_func", None))
    except Exception:  # a broken install of it is only "not installed"
        return False


def cue_facts(facts: dict, model_type: str) -> dict[str, Any]:
    """{} or {"cues": ranks}, plus `blocked` (one line) for a model in `cues.flash` while `flash_ready()` is False."""
    ranks = cues(facts, model_type)
    if not ranks:
        return {}
    flash = (facts.get("cues") or {}).get("flash") or []
    return {"cues": ranks, **({"blocked": BLOCKED} if model_type in flash and not flash_ready() else {})}
