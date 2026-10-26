"""The facts of a clip model, read from its engine catalog entry, and the sums a clip is planned with.

Pure and stdlib only; modules reach these through `hub.core.api` (`clip_facts`, `snap_frames`, `frames_for`,
`tier_size`). Every fact is the catalog's (the engine's definition of the model): nothing here names a model.
`clip_facts` gives every tier the model has; which tiers a screen offers is that module's setting.
"""
from __future__ import annotations

import math
from typing import Any

from hub.core.checks import invalid


def clip_facts(model: dict[str, Any]) -> dict[str, Any] | None:
    """None for a picture model; else {role, end, refs: {min, max, key}, fps, frames: {min, max, step, default},
    steps, tiers: [{name, sizes: {aspect: [w, h]}}], encoders}. `role` is the catalog's own word for the pictures
    the model takes ("start": a first frame; "identity": references), None when it takes none; `end` whether it
    takes a last frame too."""
    facts = model.get("video") if isinstance(model, dict) and model.get("kind") == "video" else None
    if not isinstance(facts, dict) or not facts.get("tiers"):
        return None
    refs = facts.get("references")
    refs = refs if isinstance(refs, dict) and refs.get("max") else {}
    frames = facts.get("frames")
    return {
        "role": refs.get("role"), "end": bool(refs.get("end")),
        "refs": {"min": int(refs.get("min") or 0), "max": int(refs.get("max") or 0), "key": refs.get("key")},
        "fps": facts.get("fps"), "frames": dict(frames) if isinstance(frames, dict) else None,
        "steps": facts.get("steps"),
        "tiers": [{"name": t["name"], "sizes": {a: list(s) for a, s in t["sizes"].items()}} for t in facts["tiers"]],
        "encoders": list(facts.get("text_encoders") or []),
    }


def snap_frames(facts: dict[str, Any], n: Any) -> int:
    """A clip length on the model's lattice: snapped up to the next allowed count, kept within min..max; the
    model's default when `n` is not a whole number."""
    f = facts["frames"]
    if isinstance(n, bool) or not isinstance(n, int):
        return f["default"]
    return min(f["max"], f["min"] + max(0, -(-(n - f["min"]) // f["step"])) * f["step"])


def frames_for(facts: dict[str, Any], seconds: Any) -> int:
    """The frames of a clip `seconds` long: seconds times fps, snapped (`snap_frames`); the default when `seconds`
    is not a number."""
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds):
        return facts["frames"]["default"]
    return snap_frames(facts, round(seconds * facts["fps"]))


def tier_size(facts: dict[str, Any], tier: str, aspect: str, ratio: float) -> tuple[int, int]:
    """The canvas of a clip in the tier called `tier`: its size at `aspect` when it has that, else its size nearest
    `ratio` (width over height). A tier the model does not have is refused."""
    sizes = next((t["sizes"] for t in facts["tiers"] if t["name"] == tier), None)
    if not sizes:
        raise invalid("tier", "Choose a size tier the model has")
    size = sizes.get(aspect) or min(sizes.values(), key=lambda s: abs(math.log(s[0] / s[1] / ratio)))
    return int(size[0]), int(size[1])
