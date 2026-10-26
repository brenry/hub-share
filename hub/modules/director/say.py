"""`script_say`: the Hub reads the chat message (blueprint §21). In a turn of the Hub's chat the
Hub takes the `user` message from the chat (the assistant's `said` service), not from the model: every writing
script tool (`heard`) runs this on it, once per message id; a later call of that turn answers the same line and writes
nothing. Outside such a turn (`said` None) `script_say` uses its `words` and the other tools work on their own
arguments. Which script (`_work`); the asks while the model mends (`sayask`), the message's words checked
(`saycheck`); a trial on a copy, refusals mended by the landing or sent back; one task per message, in order,
answered at `DEADLINE_S`; one write; at the limit what landed; the Hub's line, posted as `chat.note` whatever the
call answered (`saytrial`). In memory only: the tasks and `handled` {message id: (script, line)}, the last
`KEPT`. The message "render" (`RENDER`) on an open script is Render (`render.press`), its line the
answer; no model is asked. Every message is plain talk. A first message that tells a story starts the script
(no `Script:` needed); anyone may be cast, with no picture or voice (`begin.context`'s `anyone`). A message saying it is
done (`sayplain.done`) says every scene done, no model asked. Never wreck: a removal the message does not ask for
is sent back (`saycheck`), and a trial that loses lines the message does not ask to lose is sent back and, at the last
ask, not written (`_lost`). A message that asks to write and then render (`sayhold.wants_render`) is written,
then Render pressed in its answer. A new story is written in two passes (`saystory`): the Assistant's model
writes only the story as a shot list, checked and sent back with its reasons; the Hub turns it into the script as
written. One still failing at the last ask writes nothing and is answered in one plain sentence. A change to an open
script keeps the path above."""
from __future__ import annotations

import asyncio
import copy
import json
import re
import secrets
from collections.abc import Callable
from typing import Any

from hub.core.api import Ctx, Invalid, schema_check

from . import autolock, routes, sayask, saycheck, sayhold, sayplain, saystory, saytrial, scripts
from . import start as begin

DEADLINE_S = 240.0
KEPT = 20
STILL = "The Hub is still writing it; its line comes in the chat when it is done."
REPLY = "Reply with this line as written; call no other tool for this message."
DONE = "This message is done: call no other tool."
READS = ("script_read", "script_lock", "script_unlock")        # untouched (track and stems are their own)
SCRIPT = re.compile(r"\s*script\s*:\s*", re.I)
RENDER = re.compile(r"(?:please\s+)?render(?:\s+(?:it|this|the\s+(?:script|video|storyboard|cut)))?(?:\s+now)?"
                    r"(?:,?\s+please)?\s*[.!]*", re.I)            # the message "render", no model asked
handled: dict[str, tuple[str | None, str]] = {}
tasks: dict[str, asyncio.Task[tuple[str | None, str]]] = {}
_order: dict[asyncio.AbstractEventLoop, asyncio.Lock] = {}


def _said(ctx: Ctx) -> dict | None:
    try:
        got = ctx.service("said")()
    except Invalid:
        return None
    return got if isinstance(got, dict) and isinstance(got.get("text"), str) and got["text"].strip() else None


def heard(name: str, fn: Callable[[Ctx, dict], Any]) -> Callable[[Ctx, dict], Any]:
    """The writing tool `fn`, run on the `user` message instead of its arguments while the Hub's chat has a turn."""
    async def run(ctx: Ctx, args: dict) -> Any:
        got = _said(ctx)
        return await fn(ctx, args) if got is None else await message(ctx, got, name == "script_start")
    return run


async def script_say(ctx: Ctx, args: dict) -> dict:
    return await message(ctx, _said(ctx) or {"id": None, "text": args["words"], "first": False})


def _lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    if loop not in _order:
        _order.clear()
        _order[loop] = asyncio.Lock()
    return _order[loop]


async def message(ctx: Ctx, got: dict, new: bool = False) -> dict:
    """The message's task (made once per id), answered when it ends or at `DEADLINE_S`."""
    key = got.get("id") or secrets.token_hex(8)
    if key in handled:
        name, line = handled[key]
        return {"script": name, "state": [line], "next": DONE}
    again = key in tasks
    if not again:
        tasks[key] = asyncio.get_running_loop().create_task(_run(ctx, key, got, new))
    try:
        name, line = await asyncio.wait_for(asyncio.shield(tasks[key]), DEADLINE_S)
    except TimeoutError:
        return {"script": None, "state": [STILL], "next": REPLY}
    return {"script": name, "state": [line], "next": DONE if again else REPLY}


async def _run(ctx: Ctx, key: str, got: dict, new: bool) -> tuple[str | None, str]:
    async with _lock():
        try:
            name, text = await _work(ctx, got["text"], new, bool(got.get("first")))
        except Invalid as e:
            name, text = None, f"not done: {saytrial.plain(_problem(e))}"
        except Exception:  # noqa: BLE001  (no failure goes back as a refusal: the line says it)
            name, text = None, "not done: something went wrong in the Hub"
        line = saytrial.cap(f"{name}: {text}" if name else text)
        ctx.emit(autolock.NOTE, {"text": line})
        handled[key] = (name, line)
        while len(handled) > KEPT:
            handled.pop(next(iter(handled)))
        tasks.pop(key, None)
        return name, line


def _problem(e: Invalid) -> str:
    try:
        got = json.loads(e.text)
    except ValueError:
        return e.text
    return str(got.get("problem", e.text)) if isinstance(got, dict) else e.text


def _open(ctx: Ctx) -> str | None:
    from . import tools  # late: tools reads this module

    name = tools._pointer(ctx).get().get("name")
    if not isinstance(name, str) or not scripts.exists(routes.folder(ctx), name):
        return None
    try:
        scripts.opened(routes.folder(ctx), name, routes.characters(ctx))
    except Invalid:
        return None
    return name


async def _work(ctx: Ctx, text: str, new: bool, first: bool) -> tuple[str | None, str]:
    """A new story or the open script."""
    head = SCRIPT.match(text)
    words = text[head.end():].strip() if head else text.strip()
    if not new and not head and RENDER.fullmatch(words) and (name := _open(ctx)) is not None:   # the message "render"
        from . import render  # late: no model is asked

        return name, render.line(name, render.press(ctx, name))
    if not new and not head and sayplain.done(words):                       # no model asked
        name = _open(ctx)
        return (name, await _done(ctx, name, words)) if name is not None else (None, sayplain.NO_STORY)
    try:
        await ctx.service("ask")([])
    except Invalid as e:
        return None, saytrial.NO_MODEL if e.field == "model" else e.text
    name = _open(ctx)
    if new or head or name is None or first and not saycheck.is_change(words):
        return await _story(ctx, words)
    return name, await _change(ctx, name, words)


async def _story(ctx: Ctx, words: str) -> tuple[str | None, str]:
    from . import drawing, tools  # late

    folder, characters = routes.folder(ctx), routes.characters(ctx)
    try:
        held = await begin.context(ctx, words, characters, tools._names(ctx), anyone=True)
    except Invalid as e:
        return None, f"could not start the script: {saytrial.plain(_problem(e))}; send the story again"
    base = {"version": 2, "context": held, "scenes": []}
    tried = await saystory.asks(ctx, base, words, _setup(ctx, base))          # two passes
    if not tried.calls:                                  # nothing landed: no empty script left behind
        return None, sayhold.sentence(f"the story was not written: {saytrial.plain(tried.kept[0])}")
    name = _free(folder, tried.title)
    async with tools._guard():
        await asyncio.to_thread(scripts.create, folder, name, base, characters)
        ids = tools._ids(ctx)
        ids.replace({k: v for k, v in ids.get().items() if k != name})
        tools._pointer(ctx).patch({"name": name})
        tools._publish(ctx, name)
    drawing.wake(name)
    return name, await _apply(ctx, name, tried, words, True)


def _free(folder: Any, title: Any) -> str:
    try:
        name = scripts.name_of(title if isinstance(title, str) and title.strip() else "Script")
    except Invalid:
        name = "Script"
    taken, k = name, 2
    while scripts.exists(folder, taken):
        taken, k = f"{name} {k}", k + 1
    return taken


async def _change(ctx: Ctx, name: str, words: str) -> str:
    from . import tools  # late

    base = await asyncio.to_thread(scripts.opened, routes.folder(ctx), name, routes.characters(ctx))
    counters = dict(tools._ids(ctx).get().get(name, {}))
    return await _apply(ctx, name, await _asks(ctx, base, counters, words, False), words, False)


async def _done(ctx: Ctx, name: str, words: str) -> str:
    """Every scene of the open script said done, as a story's trial says them; nothing else."""
    from . import tools  # late

    base = await asyncio.to_thread(scripts.opened, routes.folder(ctx), name, routes.characters(ctx))
    counters = dict(tools._ids(ctx).get().get(name, {}))
    tried = await asyncio.to_thread(saytrial.trial, base, counters, [], words, True, *_setup(ctx, base))
    if all(sc.get("done") for sc in base["scenes"]):
        tried.calls, tried.kept = [], []
    tried.new, tried.said = False, [sayplain.EVERY if tried.calls else sayplain.ALREADY]
    return await _apply(ctx, name, tried, words, True)


def _lost(base: dict, tried: saytrial.Tried, words: str) -> list[str]:
    """The trial loses lines the message does not ask to lose: nothing of it is written; its line, sent back."""
    n = sayplain.lost(base, tried.script, words)
    if n:
        tried.calls, tried.applied = [], []
    return [sayplain.lost_line(n)] if n else []


def _setup(ctx: Ctx, base: dict) -> tuple[dict, list[str], float, set[str]]:
    from . import tools  # late

    return routes.characters(ctx), tools._names(ctx), tools._pace(ctx), set(routes.voices(ctx, base))


async def _asks(ctx: Ctx, base: dict, counters: dict, words: str, new: bool) -> saytrial.Tried:
    """Each reply checked (`saycheck`), then tried; anything kept sent back with its lines while the model mends
    (the first refused reply, or one with fewer reasons than the one before)."""
    characters, names, pace, samples = _setup(ctx, base)
    held = sayask.schema([m["name"] for m in base["context"]["cast"]], names, new)
    bare = sayask.bare(base)
    sent = sayask.messages(bare, words, new)
    best, lines, before = saytrial.Tried(copy.deepcopy(base), new), [], None
    while True:
        try:
            _, reply = await ctx.service("ask")(sent, held)
        except Invalid as e:
            best.kept = [saytrial.NO_MODEL if e.field == "model" else e.text]
            return best
        value, lines = begin.read_reply(reply), [begin.NO_JSON]
        try:
            value = schema_check(held, value) if value is not None else None
        except Invalid as e:
            value, lines = None, [e.text]
        if value is not None:
            ops, lines, bad = await asyncio.to_thread(saycheck.check, value, words, bare, new)
            pairs = [(j, op) for j, op in enumerate(ops, 1) if j not in bad]
            best = await asyncio.to_thread(saytrial.trial, base, counters, pairs, words, new, characters, names,
                                           pace, samples)
            best.title = value.get("title")
            gone = _lost(base, best, words)
            lines = lines or gone or best.kept
        best.kept = lines
        if not lines or before is not None and len(lines) >= before:
            return best
        before, sent = len(lines), [*sent, *sayask.send_back(reply, lines)]


async def _apply(ctx: Ctx, name: str, tried: saytrial.Tried, words: str, new: bool) -> str:
    """The accepted calls in one write (a refusal there: the trial once more on the file, then the write);
    -> the line after the script's name."""
    from . import tools  # late

    for again in (False, True):
        calls = tried.calls
        characters, names, pace, samples = _setup(ctx, tried.script)
        if not calls:
            return saytrial.line(tried, None, None)
        try:
            got = await tools._write(ctx, saytrial.every(calls, names, pace))
        except Invalid as e:
            if again:
                return saytrial.line(tried, None, f"not done: {saytrial.plain(_problem(e))}")
            base = await asyncio.to_thread(scripts.opened, routes.folder(ctx), name, characters)
            counters = dict(tools._ids(ctx).get().get(name, {}))
            pairs = [(k, op) for k, (op, *_) in enumerate(tried.applied, 1)]
            was, tried = tried, await asyncio.to_thread(saytrial.trial, base, counters, pairs, words, new,
                                                        characters, names, pace, samples)
            tried.title, tried.said, tried.new = was.title, was.said, was.new
            if _lost(base, tried, words):                # never written
                return saytrial.line(tried, None, "not done: it would have taken out lines nobody asked to take out")
            continue
        tried.script = await asyncio.to_thread(scripts.readable, routes.folder(ctx), name, characters)
        if sayhold.wants_render(saycheck.BEFORE_TO.split(words)[0]):      # written, then rendered
            from . import render  # late: it reads the Generate service

            tried.rendered = sayhold.rendered(render.press(ctx, name))
        return saytrial.line(tried, got, None)
    return ""

