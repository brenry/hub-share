"""The lock's two tools: `script_lock` is the press, `track.script_track` under its own
name; `script_unlock` clears the Hub's record of the last press (`lock.unlock`), the scenes' `done` untouched.
"""
from __future__ import annotations

import asyncio

from hub.core.api import Ctx

from . import answer, drawing, lock, routes, scripts, track
from .autolock import pending, said


async def script_lock(ctx: Ctx, args: dict) -> dict:
    """The press, answered as `script_track` answers."""
    return await track.script_track(ctx, args)


async def script_unlock(ctx: Ctx, args: dict) -> dict:
    """The record cleared (`measured` out) when locked; `pending` and `said` dropped, the drawing woken."""
    from . import tools  # late

    async with tools._guard():
        name, folder, characters = tools._current(ctx), routes.folder(ctx), routes.characters(ctx)
        script = await asyncio.to_thread(scripts.opened, folder, name, characters)
        done = {"did": "unlocked" if lock.locked(script) else "no record to clear", "shot": None}
        if lock.locked(script):
            script, done = await asyncio.to_thread(scripts.change, folder, name, characters, lock.unlock)
            tools._publish(ctx, name)
    pending.discard(name)
    said.pop(name, None)
    drawing.wake(name)
    return answer.state(name, tools._bare(script), done, tools._unpictured(script, characters))
