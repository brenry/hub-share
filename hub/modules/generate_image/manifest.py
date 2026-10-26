"""Generate Image: the tab, input sockets, routes, the image job kind, a Settings card, and what the tool server
publishes (the screen's settings, the model list, the push of the assistant's draft into the prompt box)."""
from __future__ import annotations

import asyncio
import contextlib

from hub.core.api import Card, Ctx, Module, Route, SocketGroup, Tab

from . import build, chain, modelfiles, models, orbit, pace, presstakes, routes, tools

_warm: set[asyncio.Task[None]] = set()


async def _load(ctx: Ctx) -> None:
    with contextlib.suppress(Exception):
        await models.catalog(ctx)


async def start(ctx: Ctx) -> None:
    """Settle the draft on disk, offer the voice's pace to the Director, then load the model list in
    the background, so the first job can be built at once."""
    routes.settle(ctx)
    from . import firstcut  # late: loaded when the module starts
    ctx.offer("first_cut", lambda: firstcut.Cut(ctx))                     # the First cut's clips
    from . import storyclip  # late: loaded when the module starts
    ctx.offer("clip_plan", lambda: storyclip.Shots(ctx))                   # the Storyboard's Render
    ctx.offer("pace", lambda: pace.read(ctx)["pace"])
    ctx.offer("sketch", lambda prompt: tools.sketch_plan(ctx, prompt))     # the Director's panels
    ctx.offer("speech", lambda: tools.speech_pick(ctx))                    # the Director's takes
    ctx.offer("cue", lambda kind: tools.cue_pick(ctx, kind))               # its cue and room takes
    ctx.offer("orbit", lambda *args: orbit.orbit_plan(ctx, *args))           # Casting's; `frames`, `views`: an extra's
    from . import pan  # late: loaded when the module starts
    ctx.offer("pan", lambda pictures, prompt, seed, length, grabs: pan.pan_plan(ctx, pictures, prompt, seed, length,
                                                                                grabs))  # the Stage tab's pan
    ctx.emit(models.READY, {})
    task = asyncio.create_task(_load(ctx))
    _warm.add(task)
    task.add_done_callback(_warm.discard)


MODULE = Module(
    id="generate-image",
    title="Generate Image",
    tab=Tab(label="Generate Image", order=10),
    lanes=("changed",),
    sockets=(SocketGroup("reference", "Reference", ("image",), 6), SocketGroup("sound", "Sound", ("audio",), 1),
             SocketGroup("video", "Video", ("video",), 1)),
    routes=(Route("GET", "/models", routes.get_models),
            Route("GET", "/weights", routes.get_weights),
            Route("POST", "/weights/rescan", routes.rescan),
            Route("PUT", "/weights/base", routes.choose_base, body_limit=4096),
            Route("GET", "/model-files", modelfiles.get_model_files),
            Route("PUT", "/model-files", modelfiles.choose_model_file, body_limit=8192),
            Route("GET", "/draft", routes.get_draft),
            Route("GET", "/characters", routes.get_characters),
            Route("PUT", "/draft", routes.put_draft, body_limit=262_144),
            Route("POST", "/seed/random", routes.random_seed),
            Route("GET", "/defaults", routes.get_defaults),
            Route("PUT", "/defaults", routes.put_defaults),
            Route("POST", "/continue", chain.continue_clip, body_limit=4096)),
    jobs={"image": presstakes.job},
    card=Card(title="Generate Image", order=880, state=routes.card),
    listens={"session.ended": routes.on_session_ended, "chat.cleared": routes.on_chat_cleared,
             "job.finished": chain.on_job_finished, "job.submitted": build.on_submitted},
    screen=tools.SCREEN,
    listings=tools.LISTINGS,
    actions=tools.ACTIONS,
    start=start,
)
