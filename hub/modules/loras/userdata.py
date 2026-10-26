"""The LoRA strengths set, kept in the hub (`<data>/loras/loras.json`), never beside the LoRA.

One entry per LoRA with a strength set: the strength, plus the file's size and mtime so a renamed or
moved file keeps its entry. Nothing else is kept about a LoRA.
"""
from __future__ import annotations

import copy
from typing import Any

from hub.core.api import Ctx, Invalid

from .scan import Entry

DOC = "loras"


def _doc(ctx: Ctx) -> Any:
    return ctx.doc(DOC, {"version": 1, "loras": {}})


def all_entries(ctx: Ctx) -> dict[str, dict[str, Any]]:
    loras = _doc(ctx).get().get("loras")
    return loras if isinstance(loras, dict) else {}


def _save(ctx: Ctx, loras: dict[str, dict[str, Any]]) -> None:
    _doc(ctx).patch({"version": 1, "loras": loras})


def reconcile(ctx: Ctx, key: str, scanned: list[Entry]) -> dict[str, dict[str, Any]]:
    """Re-key entries whose file was renamed or moved (exactly one unknown file in the family with the same size
    and mtime), refresh size/mtime, and drop entries that hold nothing. Writes only on change."""
    loras = all_entries(ctx)
    before = copy.deepcopy(loras)
    by_id = {e.id: e for e in scanned}
    unknown = [e for e in scanned if e.id not in loras]
    for old in [k for k in loras if k.startswith(key + "/") and k not in by_id]:
        rec = loras[old]
        matches = [e for e in unknown if e.size == rec.get("size") and e.mtime == rec.get("mtime")]
        if len(matches) == 1:
            loras[matches[0].id] = loras.pop(old)
            unknown.remove(matches[0])
    for lora_id in [k for k, rec in loras.items() if "strength" not in rec]:
        del loras[lora_id]
    for lora_id, rec in list(loras.items()):
        entry = by_id.get(lora_id)
        if entry is not None:
            rec["size"], rec["mtime"] = entry.size, entry.mtime
        loras[lora_id] = {k: rec.get(k) for k in ("strength", "size", "mtime")}   # nothing an older hub kept
    if loras != before:
        _save(ctx, loras)
    return loras


def _strength(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 2:
        raise Invalid("strength", "Strength must be 0 to 2")
    return round(float(value), 2)


def update(ctx: Ctx, entry: Entry, changes: Any) -> dict[str, Any]:
    """Apply {strength}; null forgets it. Returns the entry's data."""
    if not isinstance(changes, dict) or set(changes) != {"strength"}:
        raise Invalid("user", "Only the strength can change")
    loras = all_entries(ctx)
    value = changes["strength"]
    if value is None or value == "":
        loras.pop(entry.id, None)
        _save(ctx, loras)
        return {}
    loras[entry.id] = {"strength": _strength(value), "size": entry.size, "mtime": entry.mtime}
    _save(ctx, loras)
    return {"strength": loras[entry.id]["strength"]}
