"""The takes reach the chat (`autolock.py`, `trackfinish.py`, `mixfinish.py`, `track.on_finished`,
`manifest.on_finished`, `tools.script_read`): on `test_script_lock`'s Script 1 with the stand-in jobs and lane of
`test_script_mix`, the `chat.note` events the director emits caught on the fake ctx: `script_read` heads a locked script
with the takes line (running, queued, none running); a Track job's finish says one line of its own script, after its
takes are recorded and before a pending press, `; not mixed: …` when the mix was refused; a job that ended queued says
it was cancelled or failed; a Mix job's finish says the track, its one failure line or why it was not kept; a queued mix
cancelled; no answer asks for a wait and `script_read`'s schema is unchanged. A mix that lands stale says so, then the
next mix's line; the takes line reads the job's card through `FakeJobs.card`."""
from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest

from hub.core.api import Invalid
from hub.modules.director import autolock, manifest, mix, schemas, track
from tests.engine.helpers import FakeJobs
from tests.engine.test_script_autolock import edited_start
from tests.engine.test_script_lock import edited, whole
from tests.engine.test_script_mix import MixJobs, land, tracked
from tests.engine.test_script_mix import mctx as mix_ctx  # noqa: F401  (the fixture)
from tests.engine.test_script_track import call, payload, run
from tests.engine.test_script_track import ctx as track_ctx  # noqa: F401  (the fixture)

FLAGGED = {"heard": 0.62, "first_miss": 0.4, "first": 0.3, "last": 2.6}


class CardJobs(MixJobs):
    """The stand-in book with the core's `card`, as `FakeJobs` has it (`Jobs.card` in the api)."""

    card = FakeJobs.card


@pytest.fixture
def mctx(mix_ctx: Any) -> Iterator[Any]:  # noqa: F811
    mix_ctx.jobs = CardJobs(mix_ctx)
    for held in (autolock.said, autolock.pending, mix.running, mix.failed):
        held.clear()
    yield mix_ctx
    for held in (autolock.said, autolock.pending, mix.running, mix.failed):
        held.clear()


def notes(ctx: Any) -> list[str]:
    return [data["text"] for event, data in ctx.events if event == "chat.note"]


def tracks(ctx: Any) -> list[Any]:
    return [j for j in ctx.jobs.made if j.kind == "director.track"]


async def locked(ctx: Any) -> Any:
    """Script 1 written and said done: locked by the Hub, its Track job pressed -> the job."""
    await whole(ctx)
    await call(ctx, "scene_change", {"scene": 1, "done": True})
    await call(ctx, "script_track", {})                   # the done call locks nothing; Track's press does
    return tracks(ctx)[-1]


def flag_l2(made: Any) -> Any:
    names = made.plan.summary["step_names"]
    return lambda k: payload(FLAGGED) if names[k - 1].startswith("l2") else payload()


# ---------------------------------------------------------------- the takes line in script_read
async def test_script_read_heads_a_locked_script_with_the_takes_line(mctx: Any) -> None:
    made = await locked(mctx)
    made.position = 2
    read = (await call(mctx, "script_read", {}))["read"]
    assert read[1] == f"takes: Track queued (job {made.id}, 2 on the queue)"
    made.state, made.task = "running", 2
    read = (await call(mctx, "script_read", {}))["read"]
    assert read[1] == f"takes: 1 of 6 · l1 being spoken (job {made.id})"
    made.state = "done"
    await run(mctx, made, flag_l2(made))
    read = await call(mctx, "script_read", {})
    assert read["read"][1].startswith("2 takes: 1 ok, 1 flagged: l2 ") and "next" not in read
    assert not any(w in ln for ln in read["read"] for w in ("call again", "wait", "script_lock"))
    assert schemas.INPUT["script_read"] == {"type": "object", "additionalProperties": False, "required": [],
                                            "properties": {"name": {"type": "string", "minLength": 1}}}


# ---------------------------------------------------------------- a Track job's end
async def test_a_track_finish_says_one_line_of_its_own_script(mctx: Any) -> None:
    made = await locked(mctx)
    seen: list[tuple[str, int]] = []
    emit = mctx.emit
    mctx.emit = lambda event, data: (seen.append((data["text"], len(tracks(mctx)))), emit(event, data))
    await call(mctx, "event_change", {"id": "l1", "fields": {"words": "Line one, all of you."}})
    assert "Script 1" not in autolock.pending, "a write locks and presses nothing"
    mctx.doc("current", {"name": None}).patch({"name": "Other"})       # the Storyboard on another script
    made.state = "done"
    await run(mctx, made, flag_l2(made))
    assert [t for t, _ in seen] == notes(mctx)
    [(text, n)] = seen
    assert text.startswith("Script 1: 2 takes: 1 flagged: l2 ") and text.endswith(", 1 to take"), text
    assert n == 1 and len(tracks(mctx)) == 1, "no Track pressed by itself"
    await manifest.on_finished(mctx, {"job": made.id, "kind": "director.track", "state": "done", "outputs": [],
                                      "notes": {}})
    assert len(notes(mctx)) == 1, "its job.finished adds none"


async def test_the_mix_refused_in_the_finish_is_said_after_the_takes(mctx: Any, monkeypatch: Any) -> None:
    made = await locked(mctx)

    def refuse(*a: Any, **k: Any) -> Any:
        raise Invalid("mix", "a take of the mix is gone")
    monkeypatch.setattr(mix, "submit", refuse)
    made.state = "done"
    await run(mctx, made)
    assert notes(mctx) == ["Script 1: 2 takes: 2 ok; not mixed: a take of the mix is gone"]


async def test_a_queued_track_cancelled_or_refused(mctx: Any) -> None:
    made = await locked(mctx)
    made.state = "cancelled"
    await manifest.on_finished(mctx, {"job": made.id, "kind": "director.track", "state": "cancelled"})
    assert notes(mctx) == [f"Script 1: Track cancelled (job {made.id})"] and "Script 1" not in track.running
    got = await track.press(mctx, "Script 1")
    again = mctx.jobs.book[got["job"]]
    again.state, again.error = "failed", "the engine would not make that plan"
    await manifest.on_finished(mctx, {"job": again.id, "kind": "director.track", "state": "failed"})
    assert notes(mctx)[-1] == "Script 1: Track failed: the engine would not make that plan"


# ---------------------------------------------------------------- a Mix job's end
async def test_a_mix_written_says_the_track(mctx: Any) -> None:
    made = await tracked(mctx)
    await land(mctx, made)
    length = edited(mctx)["mix"]["length_ms"] / 1000
    assert notes(mctx)[-1] == f"Script 1: the track is mixed, {length:.1f} s at -23 LUFS, Sounds/Script 1.wav"


async def test_a_mix_with_nothing_landed_or_not_kept(mctx: Any) -> None:
    made = await tracked(mctx)
    await made.plan.finish({})
    assert notes(mctx)[-1] == "Script 1: the mix did not land"
    again = mix.submit(mctx, "Script 1")
    s = edited(mctx)
    s["takes"]["l1"]["file"] = "Script 1/l1-9.wav"
    from tests.engine.test_script_lock import put
    put(mctx, s)
    await land(mctx, again)
    assert notes(mctx)[-1] == "Script 1: the mix was not kept: the script changed while it mixed"


async def test_a_mix_landing_stale_is_said_then_the_next_mix(mctx: Any) -> None:
    made = await tracked(mctx)
    await call(mctx, "event_move", {"id": "l2", "start_ms": edited_start(mctx, "l2") + 500})   # while it is queued
    await land(mctx, made)
    assert notes(mctx)[-1] == "Script 1: the mix was not kept: the script changed while it mixed"
    assert mctx.jobs.made[-1] is made, "no mix pressed by itself after an edit"


async def test_a_queued_mix_cancelled(mctx: Any) -> None:
    made = await tracked(mctx)
    made.state = "cancelled"
    await manifest.on_finished(mctx, {"job": made.id, "kind": "director.mix", "state": "cancelled"})
    assert notes(mctx)[-1] == f"Script 1: the mix was cancelled (job {made.id})" and "Script 1" not in mix.running
    await manifest.on_finished(mctx, {"job": made.id, "kind": "director.mix", "state": "cancelled"})
    assert notes(mctx)[-1] == f"Script 1: the mix was cancelled (job {made.id})" and len(notes(mctx)) == 2, \
        "once: the entry is gone"


def test_no_listener_no_change() -> None:
    held = SimpleNamespace(events=[])
    held.emit = lambda event, data: held.events.append((event, data))
    autolock.note(held, "Script 1", "2 takes: 2 ok")
    assert held.events == [("chat.note", {"text": "Script 1: 2 takes: 2 ok"})]
