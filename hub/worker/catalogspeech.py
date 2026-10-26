"""A speech model's catalog facts (Stage 12): found by its definition's fields, never by its name.

A model is a speech model when its definition says it makes sound alone (`audio_only`) and its voice choices
(`audio_prompt_type_sources`, the letters its `letters_filter` or `selection` holds) take one voice sample ("A").
Its facts: the line's length the definition offers (`duration_slider`: min, max, default seconds) and the one
speaker a line has (`references` 1: one character). Stdlib only; reads definition fields, nothing of `wgp`.
"""
from __future__ import annotations

from typing import Any

SAMPLE = "A"                      # the voice choice that takes one sample (R24 §2: the speech handler's definition)
# What this module reads from the engine (R9 §3; the contract test), each tagged with the line that publishes it.
READS: dict[str, dict[str, str]] = {
    "wgp": {},
    "api": {},
    "definition": {"audio_only": "both", "audio_prompt_type_sources": "upstream", "duration_slider": "upstream"},
    "settings": {},
    "generate_video": {},
    "suffixes": {},
}


def _whole(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else None


def speech_facts(model_def: dict) -> dict[str, Any] | None:
    """{seconds: {min, max, default}, references: 1} for a speech model, else None."""
    if not model_def.get("audio_only"):
        return None
    sources = model_def.get("audio_prompt_type_sources")
    if not isinstance(sources, dict):
        return None
    letters = str(sources.get("letters_filter") or "") + "".join(str(s) for s in sources.get("selection") or ())
    if SAMPLE not in letters:
        return None
    slider = model_def.get("duration_slider")
    slider = slider if isinstance(slider, dict) else {}
    lo, hi = _whole(slider.get("min")), _whole(slider.get("max"))
    if not (lo and hi and lo <= hi):
        return None
    default = _whole(slider.get("default")) or hi
    return {"seconds": {"min": lo, "max": hi, "default": min(max(default, lo), hi)}, "references": 1}
