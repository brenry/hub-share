"""A length named for a scene is the Director's target, pure: reported on every
answer, the length asked and the length the scene runs, never a range around it and never a refusal. A scene's length
is its last shot's end less its first shot's start.
"""
from __future__ import annotations

from .layout import secs


def length(scene: dict) -> int:
    """The scene's length in ms; 0 with no shot."""
    shots = scene["shots"]
    return shots[-1]["end_ms"] - shots[0]["start_ms"] if shots else 0


def asked(scene: dict) -> str:
    """` · 15 s asked` for a scene with a length; "" without."""
    return f" · {scene['seconds']} s asked" if "seconds" in scene else ""


def shown(scene: dict, n: int) -> str:
    """The shot line's ` · scene 1 9.20 s of 15 s`; "" for a scene without a length."""
    return f" · scene {n} {secs(length(scene))} s of {scene['seconds']} s" if "seconds" in scene else ""
