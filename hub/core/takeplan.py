"""A shot's best take, the one rule the cut (`jobgraph.fill`, "best") and a scene's last step
(`api.best_take`) both ask, so they cannot disagree. Pure: no I/O, stdlib only."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def best(plan: Any, shot: int, takes: Mapping[int, Any], made: Mapping[int, Any]) -> int | None:
    """The last task of shot `shot`'s (1-based, in `plan.takes`) made take with the highest rank (its first task's
    `Take.rank`), ties the earliest; None when no take of it was made."""
    landed = [take for take in plan.takes[shot - 1] if made.get(take[-1])]
    if not landed:
        return None
    rank = {take: (tuple(takes[take[0]].rank) if take[0] in takes else ()) for take in landed}
    return max(landed, key=lambda take: (rank[take], -take[0]))[-1]
