"""Render this shot (`render.press(..., shot)`): that shot's clip, then the whole video joined again from it and every
other shot's last filed clip (`CLIPS`: {script: {shot id: clip item}}, kept by `render.Finish`). A shot with no clip
filed yet, or one that no longer reads: the shot's clip alone, no join (`items` returns None)."""
from __future__ import annotations

from typing import Any

from hub.core.api import Ctx, JoinItem

CLIPS = "shotclips"


def items(ctx: Ctx, name: str, order: list[str], part: dict) -> tuple[list[JoinItem], int] | None:
    """The join's items in shot order and the place of `part`'s own (its path filled from its task); None when
    another shot has no clip that reads."""
    held = (ctx.doc(CLIPS, {}).get() or {}).get(name) or {}
    out: list[JoinItem] = []
    at = -1
    for sid in order:
        if sid == part["id"]:
            at = len(out)
            out.append(JoinItem("", 0, part["frames"], float(part["fps"]), part["size"][0], part["size"][1],
                                part["frames"], bool(part.get("audio"))))
            continue
        item = held.get(sid)
        facts: dict[str, Any] | None = ctx.files.clip_facts(item) if item else None
        if not facts:
            return None
        n = int(facts["frames"])
        out.append(JoinItem(str(ctx.files.existing_media(item)), 0, n, float(facts["fps"]), int(facts["w"]),
                            int(facts["h"]), n, bool(facts.get("audio"))))
    return out, at


def keep(ctx: Ctx, name: str, filed: dict[str, str]) -> None:
    """Each shot's newly filed clip remembered for its script."""
    if filed:
        doc = ctx.doc(CLIPS, {})
        doc.patch({name: {**((doc.get() or {}).get(name) or {}), **filed}})


def told(summary: dict, name: str, sid: str, joined: list[JoinItem], names: list[str]) -> None:
    """The job's card for one shot and the join after it."""
    seconds = round(sum(i.frames / i.fps for i in joined), 2)
    summary.update(title=f"Render · {name} · shot {sid}", seconds=seconds,
                   step_names=[*names, f"Join · {seconds:.1f} s"])
