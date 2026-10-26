"""The Storyboard's own Video LoRAs: the `.safetensors` files in the folders set in Settings
(`modules.director.video_lora_folders`, apart from the LoRA folders Generate and the rest use), each with its
toggle and strength (`STATE`: {path: {on, strength}}, a Hub setting kept in its data folder). Only the Storyboard's
render uses them (`render`, each clip's LoRAs after its model card's), on a model that takes LoRAs; Casting, the stage
and Generate never see them."""
from __future__ import annotations

import os
from typing import Any

from hub.core.api import Ctx, Invalid

STATE = "videoloras"
STRENGTH = (0.0, 2.0)
SUFFIX = (".safetensors", ".sft")


def folders(ctx: Ctx) -> list[str]:
    held = getattr(ctx, "settings", None) or {}
    return [str(f) for f in (held.get("video_lora_folders") or []) if isinstance(f, str) and f]


def files(ctx: Ctx) -> list[str]:
    """Every LoRA file in the Video LoRA folders (subfolders too), by name."""
    out: list[str] = []
    for top in folders(ctx):
        for here, dirs, names in os.walk(top):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            out += [os.path.realpath(os.path.join(here, n)) for n in names
                    if n.lower().endswith(SUFFIX) and not n.startswith(".")]
    return sorted(dict.fromkeys(out), key=lambda p: os.path.basename(p).lower())


def listing(ctx: Ctx) -> dict[str, Any]:
    held = ctx.doc(STATE, {}).get() or {}
    return {"loras": [{"path": p, "name": os.path.basename(p), "on": bool((held.get(p) or {}).get("on")),
                       "strength": float((held.get(p) or {}).get("strength", 1.0))} for p in files(ctx)]}


def change(ctx: Ctx, body: dict) -> dict[str, Any]:
    path, known = body.get("path"), files(ctx)
    if path not in known:
        raise Invalid("path", "That LoRA is not in your Video LoRA folders")
    doc = ctx.doc(STATE, {})
    one = dict((doc.get() or {}).get(path) or {"on": False, "strength": 1.0})
    if "on" in body:
        one["on"] = bool(body["on"])
    if "strength" in body:
        v = body["strength"]
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not STRENGTH[0] <= v <= STRENGTH[1]:
            raise Invalid("strength", f"Strength is a number from {STRENGTH[0]:g} to {STRENGTH[1]:g}")
        one["strength"] = round(float(v), 2)
    doc.patch({path: one})
    return listing(ctx)


def chosen(ctx: Ctx) -> list[tuple[str, float]]:
    """The toggled-on ones still in the folders, as (full path, strength): the engine takes a full path."""
    held, there = ctx.doc(STATE, {}).get() or {}, set(files(ctx))
    return [(p, float(v.get("strength", 1.0))) for p, v in held.items() if p in there and v.get("on")]
