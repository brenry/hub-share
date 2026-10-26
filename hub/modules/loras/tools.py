"""What the LoRA library can do, declared for the tool server: the LoRAs of a model (`list_loras`)."""
from __future__ import annotations

from hub.core.api import Ctx, Listing

from . import routes


async def list_loras(ctx: Ctx, args: dict) -> dict:
    """Every LoRA in the model's folder, as the panel lists them: id, name, the file's trigger words, its default
    strength. A model without a LoRA folder has none."""
    return {"loras": [{"id": it["id"], "name": it["name"], "triggers": it["fileTriggers"],
                       "default_strength": it["defaultStrength"]}
                      for it in await routes.items(ctx, args["model"])]}


LISTINGS = (Listing("loras", "LoRAs in a model's folder: id, name, trigger words from the file, default strength.",
                    {"model": {"type": "string"}}, list_loras, required=("model",)),)
