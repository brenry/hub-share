"""The lock is the Hub's record of a Track press: `settle`, called by every press
(`track.press`), mends a version-2 script's voice fields and writes `lock {locked: true, at}` in one change, whatever
its scenes say; nothing is checked and no gap is listed. A write on a locked script unlocks it in its change
(`tools._write`), so the next press re-takes only the lines whose hash moved. `start` is
the press from a job's end, answered in one line: `Track: …` or `Track refused: …`. `script_lock` and
`script_unlock` are `lockpress.py`'s.

The takes line (`takesline.py`) heads every `script_read` of a locked or written script; at every end of
a Track or Mix job the Hub adds its own line to its chat (`note`: the core event `chat.note` {"text": "<script>:
<line>"}, which the assistant shows at once and sends on as a Hub note). In memory only: `said` {script: the last
press's line}, `pending` {script whose change came while its Track job, or its mix, ran}. Nothing of it is on disk.
The voice fields' mend is a write, timed in its change; a mix that lands stale is not kept; a change
while it mixes is `pending`, pressed once from its end (`mix_done`); the takes line reads `ctx.jobs.card`.
"""
from __future__ import annotations

import asyncio
import copy
from datetime import datetime
from pathlib import Path
from typing import Any

from hub.core.api import Ctx, Invalid

from . import landing, layout, lock, mix, routes, scripts, takesline, timing, track

NOTE = "chat.note"                       # the assistant's event (`hub/modules/assistant/chat.py`), by its name
said: dict[str, str] = {}
pending: set[str] = set()


def _mend(s: dict, counters: dict, characters: Any, pace: float) -> int | Invalid:
    """The voice fields mended, re-timed as an edit is, by `landing.write` -> the lines, or its refusal."""
    if not lock.mend(copy.deepcopy(s), pace):
        return 0
    def fn(t: dict, c: dict, ch: Any) -> dict:
        was, n = copy.deepcopy(t), lock.mend(t, pace)            # timed as `edit._settle` times every edit
        return {"did": "voice fields mended", "shot": None, "mended": n,
                "moved": timing.retime(was, t, None, "change", pace)[1]}
    trial = copy.deepcopy(s)
    try:
        done = landing.write(trial, counters, characters, fn, pace)
    except Invalid as e:
        return e
    s.clear()
    s.update(trial)
    return done["mended"]


async def settle(ctx: Ctx, name: str) -> str | None:
    """In the tools' guard, a version-2 script whose lock is off gets its voice fields mended and `lock
    {locked: true, at}` in one change -> None; locked already, version 1 or unreadable: nothing written, None. A mend
    refused: nothing written -> its one line."""
    from . import tools  # late: tools reads this module

    async with tools._guard():
        folder, characters = routes.folder(ctx), routes.characters(ctx)
        try:
            script = await asyncio.to_thread(scripts.opened, folder, name, characters)
        except Invalid:
            return None
        if script.get("version") != 2 or lock.locked(script):
            return None
        pace = tools._pace(ctx)
        at = datetime.now().astimezone().isoformat(timespec="seconds")
        counters = dict(tools._ids(ctx).get().get(name, {}))

        def change(s: dict) -> dict:
            mended = _mend(s, counters, characters, pace)         # timed as every write
            if isinstance(mended, Invalid):
                raise mended
            return {**lock.lock(s, pace, at), "mended": mended}
        try:
            await asyncio.to_thread(scripts.change, folder, name, characters, change)
        except Invalid as e:
            return lock._problem(e)
        tools._ids(ctx).patch({name: counters})
        tools._publish(ctx, name)
    return None


async def start(ctx: Ctx, name: str) -> str:
    """Track pressed (locked by the press) -> its line; refused busy or mixing, `pending`,
    pressed once."""
    try:
        got = await track.press(ctx, name)
    except track.Refusal as e:
        if e.field == "busy":
            pending.add(name)
            return f"Track: again when job {track.running.get(name, {}).get('job')} ends"
        mixing = mix.running.get(name)
        if e.field == "mix" and mixing is not None and e.text == mix.MIXING.format(name, mixing):
            pending.add(name)                                    # pressed again from the mix's end
            return f"Track: again when the mix (job {mixing}) ends"
        if e.text.startswith(mix.CURRENT):
            return "Track: " + e.text.removeprefix("nothing to render: ")
        return f"Track refused: {e.text}"
    except Exception as exc:  # noqa: BLE001  (Invalid, or the queue's Refused: its one line, as mix.after_track)
        why = lock._problem(exc) if isinstance(exc, Invalid) else getattr(exc, "text", exc)
        return f"Track refused: {why}"
    if got.get("mixing"):
        return f"Track: nothing to render; mixing (job {got['job']})"
    return f"Track: {got['lines']} lines, {got['cues']} cues (job {got['job']})"


def written(script: dict) -> bool:
    """A version-2 script with at least one line or cue."""
    return script.get("version") == 2 and any(ev["kind"] in ("line", "cue") for shot in layout.shots(script)
                                              for ev in shot["events"])


def takes_line(ctx: Ctx, name: str, script: dict, after: str | None = None) -> str:
    """The takes line of the script: its Track job's while one is queued or running, else its takes."""
    takes, held = script.get("takes") or {}, routes.voices(ctx, script)
    entry = track.running.get(name)
    card = ctx.jobs.card(entry["job"]) if entry else None          # the api's `Jobs.card`
    return takesline.line(script, card, voices={n: [v.size, v.mtime_s] for n, v in held.items()},
                          present=routes.present(ctx, takes), live=track.state(name), after=after)


def read_line(ctx: Ctx, name: str, script: dict) -> str | None:
    """`script_read`'s takes line, for a locked or written script; the last press's line after it when it is a
    refusal."""
    if not (lock.locked(script) or written(script)):
        return None
    last = said.get(name)
    return takes_line(ctx, name, script, last if last is not None and last.startswith("Track refused: ") else None)


def note(ctx: Ctx, name: str, text: str) -> None:
    """The Hub's line in its chat."""
    ctx.emit(NOTE, {"text": f"{name}: {text}"})


async def track_ended(ctx: Ctx, name: str, not_mixed: str | None) -> None:
    """A Track job's finish ran: its line, then the pending press."""
    try:
        script = await asyncio.to_thread(scripts.opened, routes.folder(ctx), name, routes.characters(ctx))
        text = await asyncio.to_thread(takes_line, ctx, name, script)
    except Invalid as e:
        text = f"the takes could not be read: {lock._problem(e)}"
    note(ctx, name, text + (f"; not mixed: {not_mixed}" if not_mixed else ""))
    await mix_done(ctx, name)                                    # the pending press, once, as from a mix's end


def track_queued(ctx: Ctx, name: str, data: dict) -> None:
    """A Track job that ended queued (cancelled or refused): its line; a cancel not undone."""
    pending.discard(name)
    if data.get("state") == "cancelled":
        note(ctx, name, f"Track cancelled (job {data.get('job')})")
    else:
        made = ctx.jobs.get(str(data.get("job")))
        note(ctx, name, f"Track failed: {getattr(made, 'error', None) or track.NO_TAKE}")


def mix_note(ctx: Ctx, name: str, got: Path | str | None, length_ms: int) -> None:
    """A Mix job's finish ran: the master as placed, why none was kept, or its one failure line."""
    if isinstance(got, Path):
        note(ctx, name, f"the track is mixed, {length_ms / 1000:.1f} s at {mix.TARGET['lufs']:g} LUFS, "
                        f"Sounds/{got.name}")
    elif isinstance(got, str):
        note(ctx, name, f"the mix was not kept: {got}")
    else:
        note(ctx, name, mix.failed.get(name, mix.NOT_LANDED))


async def mix_done(ctx: Ctx, name: str) -> None:
    """A Mix (or Track) job's finish ran, its line said: a change that came while it ran pressed once."""
    if name in pending:
        pending.discard(name)
        said[name] = await start(ctx, name)


async def mix_ended(ctx: Ctx, data: dict) -> None:
    """`job.finished` of a Mix job that `mix.running` still holds (it ended queued): dropped, its line."""
    from . import tools  # late

    if data.get("kind") != f"{ctx.module_id}.{mix.KIND}":
        return
    for name in [n for n, job in mix.running.items() if job == data.get("job")]:
        mix.running.pop(name, None)
        pending.discard(name)
        made = ctx.jobs.get(str(data.get("job")))
        tools._publish(ctx, name)
        note(ctx, name, f"the mix was cancelled (job {data.get('job')})" if data.get("state") == "cancelled"
             else str(getattr(made, "error", None) or mix.NOT_LANDED))
