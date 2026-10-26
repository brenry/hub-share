"""The sketch panels drawn, one picture job at a time (blueprint A.6; R48 §8 "the previous nail").
In memory only: the panel being drawn `{job, script, panel}` or none, each script's waiting reason, and the panels whose
job failed. `start(ctx)` (the module's start) runs one loop that waits on a wake; `wake()` sets it, and does nothing
before the start. On each wake: the fill pass (`tools.fill`); then, when no panel is being drawn, the first panel
of the current script, in script order, with no picture, not failed and whose prompt is whole (`sketch.prompt`) is
queued as a `panel` job, whose plan Generate's `sketch` service builds on the picture model picked there. A
refusal that holds for every panel (any `Invalid` but a prompt's: no picture model, a model that needs a reference,
the size, the steps; the engine offline, the queue full: `Refused`) is that script's waiting reason until the next
wake; a prompt's (`OWN`, over Generate's limit) marks that panel failed and the pass takes the next.
The loop wakes on Generate's `sketch.ready` (its start, its model list answered, a model picked), which
also clears every failed panel, on a tool write, on `script_read`, and on any job's finish while a script
waits. The finish of the job being drawn is read from the `Job` its submit returned, by `job.finished` or by the next
pass, whichever comes first (`_finish`); the slot is held until its picture is written: done -> its
first output is the panel's picture; failed or cancelled -> the panel is marked failed until the next tool write on
its script or `sketch.ready`. A stale panel (its prompt changed since it was drawn) is taken as an undrawn
one, in script order, after the job being drawn; the held slot keeps the prompt submitted, in memory, and a sketch
that finished on a changed prompt is written stale. Nothing of a job is on disk.
"""
from __future__ import annotations

import asyncio
import contextlib
import sys
from typing import Any

from hub.core.api import Ctx, Invalid, JobPlan

from . import panels, routes, scripts, sketch, stale

KIND = "panel"
READY = "sketch.ready"                   # the core event Generate emits when a sketch may be drawn, {}
TERMINAL = ("done", "failed", "cancelled")
OWN = ("prompt",)                        # the one refusal field that is a panel's own; any other waits
_state: dict[str, Any] = {"ctx": None, "event": None, "task": None, "busy": None}
waiting: dict[str, str] = {}             # script -> why its next panel waits
failed: dict[tuple[str, str], str] = {}  # (script, panel) -> the job's one-line error


def job(params: dict, ctx: Ctx) -> JobPlan:
    """The `panel` job kind: Generate's plan of one sketch picture for the prompt."""
    try:
        plan = ctx.service("sketch")
    except Invalid:
        raise Invalid("model", "Generate Image is not running") from None
    return plan(params.get("prompt"))


def wake(written: str | None = None) -> None:
    """Wake the loop; `written`: a tool wrote that script, so its failed panels are tried once more."""
    if written is not None:
        for key in [k for k in failed if k[0] == written]:
            del failed[key]
    if _state["event"] is not None:
        _state["event"].set()


def busy() -> dict | None:
    return _state["busy"]


ON_HOLD = True     # sketches flooded the queue; none are drawn while ON_HOLD is True


async def start(ctx: Ctx) -> None:
    """One loop for the module's life; the first wake now (after a restart, panels with no picture go again). On
    hold (`ON_HOLD`): no loop, so no sketch is ever drawn and `wake` does nothing."""
    if ON_HOLD:
        return
    old = _state["task"]
    if old is not None:
        old.cancel()
    _state.update(ctx=ctx, event=asyncio.Event(), busy=None)
    waiting.clear()
    failed.clear()
    _state["task"] = asyncio.create_task(_loop(ctx, _state["event"]))
    wake()


async def stop() -> None:
    task = _state["task"]
    _state.update(ctx=None, event=None, task=None, busy=None)
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def _loop(ctx: Ctx, event: asyncio.Event) -> None:
    while True:
        await event.wait()
        event.clear()
        try:
            await step(ctx)
        except Exception as exc:  # noqa: BLE001  (one line, the loop goes on)
            print(f"director: the sketch panels: {exc}", file=sys.stderr)


def _current(ctx: Ctx) -> str | None:
    name = ctx.doc("current", {"name": None}).get().get("name")
    return name if isinstance(name, str) and scripts.exists(routes.folder(ctx), name) else None


async def _lost(ctx: Ctx) -> None:
    """The job being drawn whose own `Job` is finished (the book may have forgotten it): its finish applied from
    that object, the fallback (a queued job cancelled now sends `job.finished`, cancelled). The book is
    not read for it."""
    held = _state["busy"]
    made = held["made"] if held is not None else None
    if made is not None and getattr(made, "state", None) in TERMINAL:
        await _finish(ctx, held, made.state, list(getattr(made, "outputs", None) or []), getattr(made, "error", None))


async def _finish(ctx: Ctx, held: dict, state: Any, outputs: list, error: Any) -> None:
    """The one place a finish is applied: the held panel marked finishing before the first await (the
    other reader of the same finish does nothing), the first output written as the panel's picture, or the panel
    failed with the job's one line (a write that raises: failed with its line, raised for the reader to print); the
    slot freed only then, so no pass submits while the picture is being written."""
    if _state["busy"] is not held or held.get("finishing"):
        return
    from . import tools  # late: it wakes this module

    held["finishing"] = True
    key = (held["script"], held["panel"])
    try:
        pictures = [o for o in outputs if isinstance(o, str)]
        if state == "done" and pictures:
            try:
                await tools.drawn(ctx, held["script"], held["panel"], pictures[0], held.get("prompt"))
            except Exception as exc:
                failed[key] = (str(exc).strip().splitlines() or [""])[0] or "The sketch could not be written"
                raise
        else:
            failed[key] = str(error or ("The sketch job was cancelled" if state == "cancelled"
                                        else "The sketch job made no picture"))
    finally:
        if _state["busy"] is held:
            _state["busy"] = None


def next_panel(script: dict, name: str) -> tuple[dict | None, str | None, str | None]:
    """(the first panel to draw, its prompt, the first reason a panel waits) of the script."""
    reason = None
    for n, shot, panel in panels.panels(script):
        if not stale.to_draw(panel) or (name, panel["id"]) in failed:
            continue
        text, why = sketch.prompt(script, script["scenes"][n - 1], shot, panel["at_ms"])
        if text is not None:
            return panel, text, reason
        reason = reason or why
    return None, None, reason


async def step(ctx: Ctx) -> None:
    """One wake: the fill pass, then the next job when none is being drawn."""
    from . import tools  # late: it wakes this module

    await tools.fill(ctx)
    await _lost(ctx)
    name = _current(ctx)
    if name is None or _state["busy"] is not None:
        return
    try:
        script = await asyncio.to_thread(scripts.opened, routes.folder(ctx), name, routes.characters(ctx))
    except Invalid:
        return
    waiting.pop(name, None)
    while True:
        panel, text, reason = next_panel(script, name)
        if panel is None:
            if reason is not None:
                waiting[name] = reason
            return
        try:
            made = ctx.jobs.submit(KIND, {"script": name, "panel": panel["id"], "prompt": text})
        except Invalid as exc:
            if exc.field in OWN:                 # this panel's alone; the next is taken at once
                failed[(name, panel["id"])] = exc.text or "The sketch could not be queued"
                continue
            waiting[name] = exc.text or "The sketch could not be queued"
            return
        except Exception as exc:  # noqa: BLE001  (Refused: its one line is the reason)
            waiting[name] = getattr(exc, "text", None) or str(exc) or "The sketch could not be queued"
            return
        _state["busy"] = {"job": made.id, "script": name, "panel": panel["id"], "made": made, "prompt": text}
        return


async def on_finished(ctx: Ctx, data: dict) -> None:
    """`job.finished` of the panel being drawn: applied by `_finish`; the loop wakes. Any other job's finish
    wakes the loop when a script waits (a job ran: the engine is up)."""
    held = _state["busy"]
    if held is None or data.get("tool") != ctx.module_id or data.get("job") != held["job"]:
        if waiting:
            wake()
        return
    made = held.get("made")
    try:
        await _finish(ctx, held, data.get("state"), list(data.get("outputs") or []), getattr(made, "error", None))
    finally:
        wake()


async def on_ready(ctx: Ctx, data: dict) -> None:
    """Generate's `sketch.ready`: the drawing may go on, and every failed panel of every
    script is tried once more."""
    failed.clear()
    wake()


def status(name: str, script: dict, n: int, shot: dict, panel: dict) -> str:
    """`drawing (stale <picture>)`, `drawing`, `stale <picture>[ · waiting: <reason>]`, `drawn <picture>`, `waiting`
    or `waiting: <reason>`."""
    held = _state["busy"]
    now = held is not None and held["script"] == name and held["panel"] == panel["id"]
    if panel["picture"] is not None and panel.get("stale"):
        if now:
            return f"drawing (stale {panel['picture']})"
        why = failed.get((name, panel["id"])) or sketch.prompt(script, script["scenes"][n - 1], shot,
                                                               panel["at_ms"])[1]
        return f"stale {panel['picture']}" + (f" · waiting: {why}" if why else "")
    if panel["picture"] is not None:
        return f"drawn {panel['picture']}"
    if now:
        return "drawing"
    if (name, panel["id"]) in failed:
        return f"waiting: {failed[(name, panel['id'])]}"
    _, why = sketch.prompt(script, script["scenes"][n - 1], shot, panel["at_ms"])
    why = why or waiting.get(name)
    return f"waiting: {why}" if why else "waiting"
