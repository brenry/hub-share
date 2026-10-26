"""The VRAM plan. Pure: the lane's residency in, plan out.

One image lane per GPU. A job runs at once, or, when the lane's worker holds a different model, after that is
released. Memory other programs use never holds a job: other programs share the GPU by design.
"""
from __future__ import annotations

from dataclasses import dataclass

from hub.core.api import NO_MODEL


@dataclass(frozen=True)
class Situation:
    lane: str
    model: str
    label: str                      # model label for texts
    resident: tuple[str, ...]       # models loaded in this lane
    need: int | None                # learned peak for this model on this GPU


@dataclass(frozen=True)
class Plan:
    light: str                      # green | amber
    action: str                     # run | release
    text: str
    release: tuple[str, ...] = ()   # lane ids to release before the job runs


def decide(s: Situation) -> Plan:
    if s.model == NO_MODEL:                     # a join: it loads nothing, so it never releases anything
        return Plan("green", "run", "Joining clips")
    if s.model in s.resident:
        return Plan("green", "run", f"{s.label} loaded")
    own = (s.lane,) if s.resident else ()
    if s.need is None:
        text = "First run of this model"
    else:
        text = f"Switching to {s.label}" if own else f"Loading {s.label}"
    return Plan("amber", "release" if own else "run", text, release=own)
