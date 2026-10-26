"""The Track screen holds (`hub/core/jobs.py`, `hub/modules/director/track.py`,
`manifest.py`, `routes.py`, `audioscript.py`): a take's state across reloads, one press one job, a queued job's end;
and a failed take that names only a file that landed."""
from __future__ import annotations

import dataclasses
import json
import os
import time
from collections import deque
from types import SimpleNamespace
from typing import Any

import pytest

from hub.core.api import Invalid, Job
from hub.core.jobs import Entry, JobBook
from hub.modules.director import manifest, routes, scripts, track
from tests.engine.helpers import FakeRequest
from tests.engine.test_cue_takes import cued, measured
from tests.engine.test_script_lock import whole
from tests.engine.test_script_tools import on_disk
from tests.engine.test_script_track import call, ctx, locked, payload, rows, run, sample  # noqa: F401  (fixture)


def book_of(made: Any) -> tuple[JobBook, Job, list[tuple[str, dict]]]:
    """The core's book holding the Track job `made` queued on a lane, its emits collected."""
    emitted: list[tuple[str, dict]] = []
    book = JobBook(SimpleNamespace(publish=lambda *a, **k: None), lambda: {"queue": {"max_waiting": 9}},
                   lambda k, d: emitted.append((k, d)))
    book.publish = lambda e: None                                   # type: ignore[method-assign]
    job = Job(id=made.id, kind="director.track", tool="director", state="queued", plan=made.plan, lane="L")
    book.entries[job.id] = Entry(job, {})
    book.queues["L"] = deque([job.id])
    return book, job, emitted


def changed(held: Any, since: int) -> list[dict]:
    return [d for lane, kind, d in held.bus.sent[since:] if (lane, kind) == ("changed", "changed")]


@pytest.mark.parametrize("end", ["cancel", "refuse"])
async def test_a_queued_track_job_ended_gives_the_boxes_back(ctx: Any, end: str) -> None:  # noqa: F811
    await locked(ctx)
    before = rows(ctx)
    await call(ctx, "script_track", {})
    made = ctx.jobs.made[-1]
    assert track.state("Script 1") == {"l1": ("rendering", None), "l2": ("rendering", None)}
    finished: list[Any] = []
    real = made.plan.finish

    async def spy(landed: Any) -> None:
        finished.append(landed)
        await real(landed)
    made.plan = dataclasses.replace(made.plan, finish=spy)
    book, job, emitted = book_of(made)
    if end == "cancel":
        book.cancel(job.id)
        assert job.state == "cancelled" and job.id not in book.entries, "the card leaves the queue as before"
    else:
        book.refuse(job.id, "The engine would not make it")
        assert job.state == "failed"
    [(kind, data)] = emitted
    assert kind == "job.finished" and data["state"] == ("cancelled" if end == "cancel" else "failed")
    assert data["job"] == made.id and data["kind"] == "director.track" and data["outputs"] == []
    assert not finished, "the plan's finish never runs off a lane"
    sent = len(ctx.bus.sent)
    await manifest.on_finished(ctx, data)
    assert "Script 1" not in track.running and track.state("Script 1") == {}
    assert [d["name"] for d in changed(ctx, sent)] == ["Script 1"], "one director.changed"
    assert rows(ctx) == before, "every take as it was: nothing marked failed"
    assert routes._one(ctx, "Script 1")["rendering"] is None
    await call(ctx, "script_track", {})
    assert ctx.jobs.made[-1] is not made and track.running["Script 1"]["job"] == ctx.jobs.made[-1].id, \
        "Track can be pressed again"


async def test_a_finish_that_ran_publishes_nothing_more(ctx: Any) -> None:  # noqa: F811
    await locked(ctx)
    await call(ctx, "script_track", {})
    made = ctx.jobs.made[-1]
    await run(ctx, made)
    assert "Script 1" not in track.running
    sent = len(ctx.bus.sent)
    await manifest.on_finished(ctx, {"job": made.id, "kind": "director.track", "tool": "director", "state": "done",
                                     "outputs": [], "notes": {}})
    assert len(ctx.bus.sent) == sent


async def test_another_kind_is_not_track(ctx: Any) -> None:  # noqa: F811
    await locked(ctx)
    await call(ctx, "script_track", {})
    made = ctx.jobs.made[-1]
    await track.on_finished(ctx, {"job": made.id, "kind": "director.panel", "state": "cancelled"})
    assert track.running["Script 1"]["job"] == made.id


def body(**values: Any) -> FakeRequest:
    return FakeRequest(body=json.dumps(values).encode())


async def test_rename_and_delete_refused_while_track_runs(ctx: Any) -> None:  # noqa: F811
    await locked(ctx)
    await call(ctx, "script_track", {})
    first = ctx.jobs.made[-1]
    path = ctx.files.roots["scripts"] / "Script 1.json"
    held = path.read_bytes()
    for verb, call_route, args in (("rename", routes.post_rename, {"name": "Script 1", "to": "Show2"}),
                                   ("delete", routes.post_delete, {"name": "Script 1"})):
        with pytest.raises(Invalid) as e:
            await call_route(ctx, body(**args))
        assert e.value.field == "name"
        assert e.value.text == f"Script 1's takes are rendering (job {first.id}): {verb} it when the job ends"
    assert path.read_bytes() == held and not (ctx.files.roots["scripts"] / "Show2.json").exists()
    with pytest.raises(Invalid) as e:
        await track.press(ctx, "Script 1")
    assert e.value.field == "busy" and ctx.jobs.made[-1] is first, "no second job"
    await run(ctx, first)
    assert on_disk(ctx)["takes"]["l1"]["file"] == "Script 1/l1-1.wav", "the takes filed under the name pressed"
    assert await routes.post_rename(ctx, body(name="Script 1", to="Show2")) == {"name": "Show2"}
    assert scripts.readable(routes.folder(ctx), "Show2", routes.characters(ctx))["takes"]["l1"]["file"] == \
        "Script 1/l1-1.wav"
    await routes.post_delete(ctx, body(name="Show2"))
    assert not scripts.exists(routes.folder(ctx), "Show2")


async def test_a_room_only_job_says_rendering(ctx: Any) -> None:  # noqa: F811
    await cued(ctx)
    await call(ctx, "script_track", {})
    made = ctx.jobs.made[-1]
    await run(ctx, made, lambda k: measured(k, made.plan))
    assert routes._one(ctx, "Script 1")["rendering"] is None
    script = on_disk(ctx)
    script["context"]["set"]["description"] += ", now at night"
    (ctx.files.roots["scripts"] / "Script 1.json").write_text(json.dumps(script), encoding="utf-8")
    await call(ctx, "script_track", {})
    room = ctx.jobs.made[-1]
    got = routes._one(ctx, "Script 1")
    assert {r["take"]["state"] for r in got["audio"]} == {"ok"}, "the room has no row"
    assert got["rendering"] == room.id
    await run(ctx, room, lambda k: measured(k, room.plan))
    assert routes._one(ctx, "Script 1")["rendering"] is None


async def test_an_unlocked_written_script_shows_its_rows_and_renders_nothing(ctx: Any) -> None:  # noqa: F811
    await whole(ctx)
    got = routes._one(ctx, "Script 1")
    assert [r["id"] for r in got["audio"] if r["kind"] == "line"] == ["l1", "l2"] and got["rendering"] is None
    assert not got["script"].get("lock", {}).get("locked")


async def test_a_failed_take_names_only_a_file_that_landed(ctx: Any) -> None:  # noqa: F811
    await locked(ctx)
    await call(ctx, "script_track", {})
    made = ctx.jobs.made[-1]
    await run(ctx, made, lambda k: None if k <= 3 else payload())
    assert rows(ctx)["l1"]["take"] == {"state": "failed", "why": "take failed: out of memory 3"}
    await call(ctx, "script_track", {})
    await run(ctx, ctx.jobs.made[-1])
    assert rows(ctx)["l1"]["take"]["file"] == "Script 1/l1-1.wav"
    voice = sample(ctx, "Character 7", 3.0)                     # l1 goes stale; its take stays in Sounds
    os.utime(voice, (time.time() + 5, time.time() + 5))
    await call(ctx, "script_track", {})
    await run(ctx, ctx.jobs.made[-1], lambda k: None)
    assert rows(ctx)["l1"]["take"] == {"state": "failed", "file": "Script 1/l1-1.wav",
                                       "why": "take failed: out of memory 3"}
