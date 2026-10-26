"""LoRAs: the library behind Generate Image's LoRA panel; the strengths set; the list the tool server gives."""
from __future__ import annotations

import asyncio
from typing import Any

from hub.core.api import Ctx, Module, Route

from . import routes, scan, tools, userdata


async def on_folders(ctx: Ctx, data: dict[str, Any]) -> None:
    """The LoRA folders changed: rescan every family (strengths follow moved files)."""
    try:
        cat = await ctx.engine.query("models")
    except Exception:
        return
    for fam in scan.families(cat).values():
        userdata.reconcile(ctx, fam.key, await asyncio.to_thread(scan.scan, fam))


MODULE = Module(
    id="loras",
    title="LoRAs",
    routes=(Route("GET", "", routes.list_loras),
            Route("PATCH", "/user", routes.patch_user),
            Route("GET", "/thumb", routes.thumb)),
    listens={"settings.lora_folders": on_folders},
    listings=tools.LISTINGS,
)
