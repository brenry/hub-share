"""The Director: the Storyboard tab and its routes, the script tools on the MCP server and the lane the tab
follows, and the sketch panels: one `panel` picture job at a time, built by Generate's `sketch`
service, its `job.finished` writing the picture into the script; `Track`: the `track` job and the
`script_track` tool after `script_unlock`; the mix: the `mix` job and `script_stems` last. No sockets, no
card. `job.finished` also reaches `track.on_finished` and `autolock.mix_ended`.
Render: the `render` job and the `script_render` tool last (`render.py`), its routes `/render` and
`/edit` (`owner.py`)."""
from __future__ import annotations

from hub.core.api import Ctx, Module, Tab

from . import autolock, drawing, mix, render, routes, tools, track


async def on_finished(ctx: Ctx, data: dict) -> None:
    """`job.finished`: the sketch panel's, then a Track job whose finish never ran, then a
    Mix job's."""
    try:
        await drawing.on_finished(ctx, data)
    finally:
        try:
            await track.on_finished(ctx, data)
        finally:
            await autolock.mix_ended(ctx, data)


MODULE = Module(
    id="director",
    title="Storyboard",
    tab=Tab(label="Storyboard", order=30),
    lanes=("changed",),
    routes=routes.ROUTES,
    actions=(*tools.ACTIONS, track.ACTION, mix.ACTION, render.ACTION),
    jobs={drawing.KIND: drawing.job, track.KIND: track.job, mix.KIND: mix.job, render.KIND: render.job},
    listens={"job.finished": on_finished, drawing.READY: drawing.on_ready},
    start=routes.start,
)
