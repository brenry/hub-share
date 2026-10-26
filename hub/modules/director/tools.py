"""The script tools on the Hub's MCP server (blueprint A.3, R48 §2): the `Action`s of `ACTIONS`, their descriptions
from `teach.py`, their schemas from `schemas.py`, one event per call, each checked on arrival. They
act on the script the module's pointer names (`current`): `script_start` and `script_read {name}` set it; renaming
it on the tab moves it, deleting it clears it (`routes.py`). One pointer: two chats writing scripts at once write the
same one. A write answers ≤ 6 lines and publishes `director.changed {name, revision}`; a refusal answers
`{problem, fix, hints}`, the file untouched and nothing published, but `scene_change`'s (written first).
A write takes the sketch panels out before its change and puts back those whose cause stands
(`panels.py`), then wakes the drawing (`drawing.py`), whose pass adds the missing panels under the same guard (`fill`).
`script_read` runs that pass first and wakes the drawing too. The drawing writes nothing to
a locked script. A write on a locked script unlocks it in its change (`autolock.py`); only
a Track press locks it (`track.press`); `script_read` gives the takes line; `script_lock` and `script_unlock`
are `lockpress`'s. `script_say` is `say.py`'s, and in a turn of the
Hub's chat every writing tool runs it on the `user` message (`say.heard`).
"""
from __future__ import annotations

import asyncio
import copy
import json
import time
from collections.abc import Callable
from typing import Any

from hub.core.api import Action, Ctx, Invalid

from . import (
    answer,
    autolock,
    drawing,
    edit,
    frame,
    landing,
    layout,
    lock,
    lockpress,
    panels,
    refs,
    routes,
    say,
    schemas,
    scripts,
    stale,
)
from . import context as scene_context
from . import start as begin
from .teach import SAY

_locks: dict[asyncio.AbstractEventLoop, asyncio.Lock] = {}


def _guard() -> asyncio.Lock:
    """One tool write at a time: the id counters are read and written under it. One lock per running
    event loop, made on first use, so a lock is never met on a loop it is not bound to (the Hub runs one loop)."""
    loop = asyncio.get_running_loop()
    if loop not in _locks:
        _locks.clear()                       # an old loop's lock is never used again
        _locks[loop] = asyncio.Lock()
    return _locks[loop]


def _pointer(ctx: Ctx) -> Any:
    return ctx.doc("current", {"name": None})


def _ids(ctx: Ctx) -> Any:
    return ctx.doc("ids", {})


def _current(ctx: Ctx) -> str:
    name = _pointer(ctx).get().get("name")
    if not isinstance(name, str) or not scripts.exists(routes.folder(ctx), name):
        raise edit.refuse("No script is open", "Call script_start, or script_read with a name")
    return name


def _pace(ctx: Ctx) -> float:
    """The Hub's pace: Generate's measured words per second; the engine's 2.6 when it offers none."""
    try:
        return float(ctx.service("pace")())
    except Invalid:
        return layout.PACE


def _publish(ctx: Ctx, name: str) -> None:
    ctx.bus.publish("changed", "changed", {"name": name, "revision": time.time_ns() // 1000})


def _landed(e: Invalid, call: tuple[str, dict], base: dict, characters: Any, counters: dict, pace: float) -> Invalid:
    """The refusal with its correction tried (`landing.land`) on copies of `base`, the file as read."""
    try:
        got = json.loads(e.text)
    except ValueError:
        return e
    bare = _bare(base)
    resolved = refs.call(bare, call)                     # landing sees the call by id
    if not isinstance(got, dict) or not isinstance(got.get("hints"), dict) or resolved is None:
        return e
    attempt = landing.attempts(base, characters, counters, pace, lambda tool, args: _edit(tool, args, pace))
    out = landing.land(resolved[0], resolved[1], got, bare, attempt)
    return edit.refuse(out["problem"], out["fix"], **out["hints"])


async def _write(ctx: Ctx, fn: Callable[[dict, dict, dict], dict], call: tuple[str, dict] | None = None,
                 named: str | None = None) -> dict:
    """`fn(script, counters, characters)` on the current script (`named`, the Storyboard's), in one locked
    read-change-write; -> the write's answer (`answer.py`). A refusal of the event tool `call` (name, args) is sent
    with its correction tried. A locked script unlocked in the change."""
    async with _guard():
        name, pace, folder = named or _current(ctx), _pace(ctx), routes.folder(ctx)
        characters = routes.characters(ctx)
        counters = dict(_ids(ctx).get().get(name, {}))
        def change(s: dict) -> dict:
            if lock.locked(s):
                lock.unlock(s)                           # a refused write changes nothing
            return landing.write(s, counters, characters, fn, pace)
        try:
            script, done = await asyncio.to_thread(scripts.change, folder, name, characters, change)
        except Invalid as e:
            if call is None:
                raise
            base = await asyncio.to_thread(scripts.opened, folder, name, characters)
            raise await asyncio.to_thread(_landed, e, call, base, characters,
                                          dict(_ids(ctx).get().get(name, {})), pace) from None
        _ids(ctx).patch({name: counters})
        _publish(ctx, name)
    drawing.wake(name)
    return answer.state(name, _bare(script), done, _unpictured(script, characters))


def _unpictured(script: dict, characters: Any) -> list[str]:
    """The cast with no picture in Characters, for the answer's first line (none in version 1)."""
    return scene_context.unpictured(script["context"], characters) if "context" in script else []


def _bare(script: dict) -> dict:
    """A copy of the script without its panels (what the answers read)."""
    bare = copy.deepcopy(script)
    panels.strip(bare)
    return bare


def _exists(ctx: Ctx) -> Callable[[str], bool]:
    """Whether a panel's picture is still a picture in Media (`ctx.files.existing_image`)."""
    def exists(item: str) -> bool:
        try:
            ctx.files.existing_image(item)
        except Invalid:
            return False
        return True
    return exists


async def fill(ctx: Ctx) -> None:
    """A panel for each cause of the current script with none, and not drawn each panel
    whose picture is gone from Media, in one locked change, published; no write and no publish when nothing changes
    (or no version-2 script is open)."""
    await _fill(ctx)


async def _fill(ctx: Ctx) -> bool:
    async with _guard():
        name = _pointer(ctx).get().get("name")
        folder, characters = routes.folder(ctx), routes.characters(ctx)
        if not isinstance(name, str) or not scripts.exists(folder, name):
            return False
        try:
            script = await asyncio.to_thread(scripts.opened, folder, name, characters)
        except Invalid:
            return False
        if lock.locked(script):
            return False
        exists = _exists(ctx)
        if not panels.missing(script) and not await asyncio.to_thread(panels.forget, script, exists):
            return False
        counters = dict(_ids(ctx).get().get(name, {}))
        await asyncio.to_thread(scripts.change, folder, name, characters,
                                lambda s: {"forgot": panels.forget(s, exists), "added": panels.fill(s, counters)})
        _ids(ctx).patch({name: counters})
        _publish(ctx, name)
    return True


async def drawn(ctx: Ctx, name: str, panel: str, picture: str, prompt: str | None = None) -> None:
    """The panel's picture written (stale when its prompt is not `prompt`), published."""
    async with _guard():
        folder, chars = routes.folder(ctx), routes.characters(ctx)
        try:
            script = await asyncio.to_thread(scripts.opened, folder, name, chars)
        except Invalid:
            return
        if panels.find(script, panel) is None or lock.locked(script):
            return                                       # the picture stays in Temp
        await asyncio.to_thread(scripts.change, folder, name, chars, lambda s: stale.drawn(s, panel, picture, prompt))
        _publish(ctx, name)


def _names(ctx: Ctx) -> list[str]:
    return [c["name"] for c in ctx.files.characters()]


def _name(value: str) -> str:
    try:
        return scripts.name_of(value)
    except Invalid as e:
        raise edit.refuse(e.text, "Use a short title without slashes") from None


async def script_start(ctx: Ctx, args: dict) -> dict:
    name = _name(args["name"])
    folder = routes.folder(ctx)
    if scripts.exists(folder, name):
        raise edit.refuse(f"A script named {name} already exists", "Use another name, or script_read with this "
                          "name to go on writing it")
    characters = routes.characters(ctx)
    held = await begin.context(ctx, args["story"], characters, _names(ctx))
    script = {"version": 2, "context": held, "scenes": []}
    async with _guard():
        await asyncio.to_thread(scripts.create, folder, name, script, characters)
        ids = _ids(ctx)
        ids.replace({k: v for k, v in ids.get().items() if k != name})
        _pointer(ctx).patch({"name": name})
        _publish(ctx, name)
    drawing.wake(name)
    return answer.state(name, script, {"did": f"started {name} · context written", "shot": None, "next": answer.WRITE})


async def script_read(ctx: Ctx, args: dict) -> dict:
    if "name" in args:
        name = _name(args["name"])
        if not scripts.exists(routes.folder(ctx), name):
            raise edit.refuse(f"There is no script named {name}", "Name a script of the Scripts folder",
                              scripts=scripts.names(routes.folder(ctx)))
        _pointer(ctx).patch({"name": name})
    else:
        name = _current(ctx)
    await fill(ctx)                          # its panel lines current, then the drawing woken
    drawing.wake()
    script = await asyncio.to_thread(scripts.readable, routes.folder(ctx), name, characters := routes.characters(ctx))
    if script["version"] == 1:
        return answer.read(name, script, pace=_pace(ctx))              # the gap calls at the measured pace
    edit.ensure_shot_ids(script, dict(_ids(ctx).get().get(name, {})))   # the ids its first write gives
    read = answer.read(name, _bare(script), _unpictured(script, characters), routes.track_state(ctx, name, script),
                       pace=_pace(ctx), takes=await asyncio.to_thread(autolock.read_line, ctx, name, script))
    read["read"] += [f"{p['id']} panel {shot.get('id', '?')} {_at(shot, p['at_ms'])} · "
        f"{drawing.status(name, script, n, shot, p)}{answer.tracked(p)}" for n, shot, p in panels.panels(script)]
    return read


def _at(shot: dict, ms: int) -> str:
    """The terms: the offset from the shot's start and the script time."""
    return f"{layout.secs(ms - shot['start_ms'])} (script {layout.secs(ms)})"


async def context_set(ctx: Ctx, args: dict) -> dict:
    names = _names(ctx)
    pace = _pace(ctx)                                    # a removal times the script again
    return await _write(ctx, lambda s, c, chars: frame.context_set(s, args, chars, names, pace=pace))


EDITS = {"line_add": (edit.line_add, True), "cue_add": (edit.cue_add, True), "pose_add": (edit.pose_add, True),
         **{k: (fn, False) for k, fn in refs.TOOLS.items()}}   # a ref resolved first


def _edit(tool: str, args: dict, pace: float) -> Callable[[dict, dict, dict], dict]:
    fn, counted = EDITS[tool]
    return (lambda s, c, chars: fn(s, c, args, pace=pace)) if counted else (lambda s, c, chars: fn(s, args, pace=pace))


def _tool(fn: Callable[..., dict], counted: bool, timed: bool = True) -> Callable[[Ctx, dict], Any]:
    """A tool on `_write`; an event tool (`timed`) is handed the Hub's pace, read on each write."""
    call = next((k for k, (f, _) in EDITS.items() if f is fn), None)

    async def run(ctx: Ctx, args: dict) -> dict:
        extra = {"pace": _pace(ctx)} if timed else {}
        return await _write(ctx, (lambda s, c, chars: fn(s, c, args, **extra)) if counted
                            else (lambda s, c, chars: fn(s, args, **extra)), None if call is None else (call, args))
    return run


FNS = {"script_start": script_start, "context_set": context_set, "scene_add": _tool(frame.scene_add, False, True),
       "scene_change": _tool(frame.scene_change, False, True), "shot_add": _tool(frame.shot_add, True, False),
       "line_add": _tool(edit.line_add, True), "cue_add": _tool(edit.cue_add, True),
       "pose_add": _tool(edit.pose_add, True), **{k: _tool(fn, False) for k, fn in refs.TOOLS.items()},
       "script_read": script_read, "script_lock": lockpress.script_lock, "script_unlock": lockpress.script_unlock}
FNS = {"script_say": say.script_say, **{n: say.heard(n, fn) if n not in say.READS else fn for n, fn in FNS.items()}}
ACTIONS = tuple(Action(n, SAY[n], schemas.INPUT[n], FNS[n]) for n in schemas.INPUT)
