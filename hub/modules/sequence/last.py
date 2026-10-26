"""The newest clip Generate Image made in this session (memory only, like Generate's `last_clip`): what
`add_last_clip` adds. A finished Generate job's newest clip output replaces it; the session's end forgets it."""
from __future__ import annotations

from pathlib import Path

from hub.core.api import Ctx

GENERATE = "generate-image.image"
_last: dict[Path, str] = {}


def clip(ctx: Ctx) -> str | None:
    return _last.get(ctx.data_dir)


async def on_finished(ctx: Ctx, data: dict) -> None:
    if data.get("kind") != GENERATE or data.get("state") != "done":
        return
    made = [o for o in data.get("outputs") or [] if isinstance(o, str) and ctx.files.kind(o) == "clip"]
    if made:
        _last[ctx.data_dir] = made[-1]


async def on_ended(ctx: Ctx, data: dict) -> None:
    _last.pop(ctx.data_dir, None)
