"""Saved model ids across engine lines: when the engine line renames models (its catalog entries say what each was
called on the line the Hub ran before, `was`), the ids the Hub saved there are brought over once (`adopt`).
"""
from __future__ import annotations

from typing import Any

from hub.core.api import Ctx

from . import models, routes


def _keys(old: dict[str, str], d: Any) -> Any:
    """A per-model object with each renamed key under its new id; an entry the model already has there is kept."""
    if not isinstance(d, dict):
        return d
    staying = {k for k in d if k not in old}
    return {old.get(k, k): v for k, v in d.items() if k not in old or old[k] not in staying}


def carry(old: dict[str, str], part: dict[str, Any]) -> dict[str, Any]:
    """Saved fields as the line before named them, brought over: the model, the last picks, the per-model keys."""
    out = dict(part)
    if isinstance(out.get("model"), str):
        out["model"] = old.get(out["model"], out["model"])
    if isinstance(out.get("lastModel"), dict):
        out["lastModel"] = {k: old.get(v, v) if isinstance(v, str) else v for k, v in out["lastModel"].items()}
    for name in ("advancedByModel", "lorasByModel"):
        if name in out:
            out[name] = _keys(old, out[name])
    return out


def adopt(ctx: Ctx, cat: dict | None) -> None:
    """The ids saved on the engine line the Hub ran before, brought over once to the catalog's line when its models
    say what they were called there (`was`, `models.renamed`): the draft's model, its last picks, the keys of its
    per-model settings (`carry`) and the defaults each take the model's id now. An id the new line gives to another
    model (the upstream adapter's facts file names the one trap) is renamed too, which is why this runs once per move:
    the draft then names the line (`engine`), and every id saved after it is the line's own. A line that renames
    nothing changes no id; it is recorded only over another line's name, so going back to it and forward again brings
    the ids saved in between over again."""
    line = ((cat or {}).get("engine") or {}).get("api")
    old = models.renamed(cat)
    doc = ctx.doc(routes.DRAFT, {})
    draft = dict(doc.get())
    if not isinstance(line, str) or draft.get("engine") == line or not (old or draft.get("engine")):
        return
    draft = {**carry(old, draft), "engine": line}
    doc.replace({k: v for k, v in draft.items() if k in routes.SAVED_FIELDS and v is not None})
    if old:
        chosen, none = ctx.doc(routes.DEFAULTS, routes.NO_DEFAULTS), routes.NO_DEFAULTS
        chosen.replace({**none, **{k: old.get(v, v) for k, v in chosen.get().items() if k in none}})
        ctx.bus.publish("changed", "draft", {})


def window(part: dict[str, Any], saved: dict[str, Any], cat: dict | None) -> dict[str, Any]:
    """A window's change, as `put_draft` takes it. A window that loaded the draft before the move names no line or
    another (`engine`, which every save carries): its model and per-model keys are brought over as `adopt` brought
    the saved ones (`carry`). A window that loaded after it sends the line's own ids, kept as they are."""
    if "engine" not in saved or part.get("engine") == saved["engine"]:
        return part
    return carry(models.renamed(cat), part)
