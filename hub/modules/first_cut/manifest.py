"""The First cut: a mixed script rendered as one rough MP4, a Ref2VA clip per shot on its slice of the
track, joined with the whole track as its one sound. Its routes, the `render` job and its `job.finished`
listener; no tab (the Storyboard's Render is the only render; its `cast_pictures` service stays for it).
It imports nothing of another module: the clips are Generate's service `first_cut`, the script is read from its
file (`script.read`). No sockets, no card."""
from __future__ import annotations

import asyncio

from hub.core.api import Ctx, Module

from . import pictures, render, routes, slices


async def start(ctx: Ctx) -> None:
    """Slices a Hub that stopped mid-job left, older than a day, removed; the cast's pictures offered to the
    Storyboard's Render."""
    ctx.offer("cast_pictures", lambda shot, who, cap, label: pictures.pick(ctx, shot, who, cap, label))
    await asyncio.to_thread(slices.sweep, ctx)


MODULE = Module(
    id="first-cut",
    title="First cut",
    lanes=("changed",),
    routes=routes.ROUTES,
    jobs={render.KIND: render.job},
    listens={"job.finished": routes.on_finished},
    start=start,
)
