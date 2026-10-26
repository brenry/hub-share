"""The Hub locks at the press (`hub/modules/director/autolock.py`, `tools._write`, `lock.lock`, `edit.line_add`,
`frame.scene_change`, `track.py`, `routes._one`): on `test_script_lock`'s Script 1 with stand-in samples, speech model,
jobs and lane (`test_script_track`, `test_script_mix`): a bare line stores the Hub's voice defaults and an old one is
mended by the press; any press locks a written script whatever its scenes say and lists no gap; a short sample is
Track's own refusal; a press refused busy is pressed again from the job's finish with only the changed line
(`autolock.start`), a cancel is not undone; a write on a locked script lands, unlocks it and the next press re-takes
only what its hash marks; `/script` answers `audio` for every written script; no answer names a lock or a gap. A file
whose lines lack the lock's fields locks on one settle (its mend timed), a mend refused writes nothing; a move while the
mix is queued presses once after it, a cancelled mix leaves nothing pending."""
from __future__ import annotations

import copy
from collections.abc import Iterator
from typing import Any

import pytest

from hub.core.api import Invalid
from hub.modules.director import autolock, lock, mix, panels, routes, track
from tests.engine.test_script_lock import edited, line, put, whole
from tests.engine.test_script_mix import land, mctx, tracked  # noqa: F401  (the fixture)
from tests.engine.test_script_tools import refused
from tests.engine.test_script_track import call, run, sample
from tests.engine.test_script_track import ctx as track_ctx  # noqa: F401  (the fixture)

WORDS = ("not complete", "not locked", "locks when", "paused", " · locked", "gaps:", "mend each with the call it names")
HELLO = {"shot": "s1", "speaker": "Character 7", "words": "Hello."}


@pytest.fixture(autouse=True)
def clean() -> Iterator[None]:
    """The module's memory empty before and after each test."""
    for held in (autolock.said, autolock.pending, mix.running, mix.failed):
        held.clear()
    yield
    for held in (autolock.said, autolock.pending, mix.running, mix.failed):
        held.clear()


def said(answer: dict) -> list[str]:
    return [*answer.get("state", []), *answer.get("read", []), *answer.get("gaps", [])]


def tracks(ctx: Any) -> list[Any]:
    return [j for j in ctx.jobs.made if j.kind == "director.track"]


async def locks(ctx: Any) -> dict:
    """`script_lock`, the press, answered as `script_track`."""
    return await call(ctx, "script_lock", {})


def pressed_line(got: dict) -> str:
    """The press's first line, `Script 1 · Track: …`."""
    return got["state"][0]


# ---------------------------------------------------------------- a bare line's voice fields
async def test_a_bare_line_stores_the_hubs_pace_and_no_language_or_emotion(mctx: Any) -> None:  # noqa: F811
    mctx.service_pace = 2.4567
    base = mctx.service
    mctx.service = lambda name: (lambda: mctx.service_pace) if name == "pace" else base(name)
    await whole(mctx)
    await call(mctx, "line_add", HELLO)
    bare = line(edited(mctx), "l3")
    assert bare["pace"] == 2.46 and "language" not in bare and "emotion" not in bare, "the pace, no language or emotion"
    await call(mctx, "line_add", {**HELLO, "language": "Language 1", "emotion": "Emotion 1"})
    assert (line(edited(mctx), "l4")["language"], line(edited(mctx), "l4")["emotion"]) == ("Language 1", "Emotion 1")
    await call(mctx, "line_add", HELLO)
    assert "language" not in line(edited(mctx), "l5"), "the language another line names is not taken"


async def test_an_old_bare_line_is_mended_by_the_lock_and_never_a_gap(mctx: Any) -> None:  # noqa: F811
    await whole(mctx)
    script = edited(mctx)
    for k in ("language", "emotion", "pace"):
        line(script, "l2").pop(k, None)
    put(mctx, script)
    got = await locks(mctx)
    assert pressed_line(got).startswith("Script 1 · Track: 2 lines rendering") and "gaps" not in got
    held = line(edited(mctx), "l2")
    assert held["pace"] == 2.6 and "language" not in held and "emotion" not in held, "the pace alone"


def hub_pace(ctx: Any, pace: float) -> None:
    base = ctx.service
    ctx.service = lambda name: (lambda: pace) if name == "pace" else base(name)


async def unlocked_file(ctx: Any) -> dict:
    """Script 1 as a file whose lines lack the lock's fields: bare lines timed at the Hub's 2.4537 words/s, every
    scene done -> it."""
    hub_pace(ctx, 2.4537)
    await whole(ctx)
    script = edited(ctx)
    for ident in ("l1", "l2"):
        line(script, ident)["pace"] = 2.4537
    put(ctx, script)
    await call(ctx, "event_change", {"id": "l1", "fields": {"emotion": "warm"}})     # timed at 2.4537
    script = edited(ctx)
    for ident in ("l1", "l2"):
        for k in lock.FIELDS:
            line(script, ident).pop(k, None)
    put(ctx, script)
    trial = copy.deepcopy(script)
    assert lock.lock(trial, 2.4537, "now")["mended"] == 2, "both lines lack the pace"
    return script


# ---------------------------------------------------------------- a file whose lines lack the lock's fields
async def test_an_unlocked_file_locks_on_one_settle(mctx: Any) -> None:  # noqa: F811
    await unlocked_file(mctx)
    assert await autolock.settle(mctx, "Script 1") is None
    assert edited(mctx)["lock"]["locked"] is True and not tracks(mctx), "settle locks; the press takes"
    assert [line(edited(mctx), i)["pace"] for i in ("l1", "l2")] == [2.45, 2.45]


async def test_a_mend_refused_writes_nothing(mctx: Any, monkeypatch: Any) -> None:  # noqa: F811
    before = await unlocked_file(mctx)

    def refuse(*a: Any, **k: Any) -> dict:
        raise Invalid("script", "s1 at 2.00–3.00 s: 1.00 s the mend would leave")
    monkeypatch.setattr(autolock.landing, "write", refuse)
    got = await refused(mctx, "script_lock", {})
    assert edited(mctx) == before, "the file unchanged"
    assert got["problem"] == "s1 at 2.00–3.00 s: 1.00 s the mend would leave" and not tracks(mctx)


# ---------------------------------------------------------------- any press locks
async def test_track_locks_a_script_with_no_scene_done(mctx: Any) -> None:  # noqa: F811
    await whole(mctx)
    await call(mctx, "scene_add", {"title": "Two", "cast": ["Character 7"]})
    await call(mctx, "shot_add", {"scene": 2, "camera": {"framing": "Close on Character 7", "on": ["Character 7"]}})
    await call(mctx, "line_add", {"shot": "s2", "speaker": "Character 7", "words": "Line 1."})
    from tests.engine.test_script_stale import draw_all
    await draw_all(mctx)
    assert not any("done" in sc for sc in edited(mctx)["scenes"])
    last = await locks(mctx)
    [job] = tracks(mctx)
    assert pressed_line(last).startswith("Script 1 · Track: 3 lines rendering") and \
        pressed_line(last).endswith(f"(job {job.id})") and edited(mctx)["lock"]["locked"] is True
    assert not any("done" in sc for sc in edited(mctx)["scenes"]), "nothing marked done"
    assert job.plan.summary["model_id"] == "h3", "B7's speech model"


async def test_a_short_sample_is_one_line_naming_the_file(mctx: Any) -> None:  # noqa: F811
    await whole(mctx)
    sample(mctx, "Character 7", 1.4)
    with pytest.raises(Invalid) as e:
        await locks(mctx)
    assert "l1: Character 7's voice sample is 1.40 s, under 2 s" in e.value.text and not tracks(mctx)
    assert edited(mctx)["lock"]["locked"] is True, "a refused press leaves the record"
    await call(mctx, "line_add", HELLO)
    assert edited(mctx)["lock"]["locked"] is False
    assert await autolock.start(mctx, "Script 1") == \
        "Track refused: l1: Character 7's voice sample is 1.40 s, under 2 s"
    assert edited(mctx)["lock"]["locked"] is True and not tracks(mctx)


async def test_a_gap_of_the_old_checklist_stops_nothing(mctx: Any) -> None:  # noqa: F811
    await whole(mctx)
    script = edited(mctx)
    del script["scenes"][0]["shots"][0]["camera"]["on"]
    put(mctx, script)
    got = await locks(mctx)
    assert pressed_line(got).startswith("Script 1 · Track: 2 lines rendering") and "gaps" not in got
    assert edited(mctx)["lock"]["locked"] is True and len(tracks(mctx)) == 1


async def test_a_stale_sketch_waits_for_nothing(mctx: Any) -> None:  # noqa: F811
    await whole(mctx)
    script = edited(mctx)
    [(_, _, f)] = [(n, s, p) for n, s, p in panels.panels(script)][:1]
    panels.find(script, f["id"])[2]["stale"] = True
    put(mctx, script)
    await locks(mctx)
    assert edited(mctx)["lock"]["locked"] is True and len(tracks(mctx)) == 1


# ---------------------------------------------------------------- a change while Track runs
async def test_a_change_while_track_runs_is_pressed_from_its_finish_with_only_that_line(mctx: Any) -> None:  # noqa
    await whole(mctx)
    await locks(mctx)
    [first] = tracks(mctx)
    await call(mctx, "event_change", {"id": "l1", "fields": {"words": "Line one, all of you."}})
    assert not autolock.pending and edited(mctx)["lock"]["locked"] is False, "a write unlocks"
    with pytest.raises(Invalid) as e:
        await locks(mctx)
    assert f"Script 1's takes are rendering (job {first.id})" in e.value.text, "script_track's busy refusal"
    assert await autolock.start(mctx, "Script 1") == f"Track: again when job {first.id} ends"
    assert "Script 1" in autolock.pending
    assert len(tracks(mctx)) == 1
    await run(mctx, first)
    [_, second] = tracks(mctx)
    assert second.plan.summary["step_names"] == ["l1", "l1 · take 2", "l1 · take 3"], "only the changed line"
    assert not autolock.pending


async def test_a_queued_job_cancelled_leaves_nothing_pending(mctx: Any) -> None:  # noqa: F811
    await whole(mctx)
    await locks(mctx)
    [first] = tracks(mctx)
    await call(mctx, "event_change", {"id": "l1", "fields": {"words": "Line one, all of you."}})
    await autolock.start(mctx, "Script 1")
    assert "Script 1" in autolock.pending
    first.state = "cancelled"
    await track.on_finished(mctx, {"job": first.id, "kind": "director.track", "state": "cancelled"})
    assert not autolock.pending and len(tracks(mctx)) == 1 and "Script 1" not in track.running


# ---------------------------------------------------------------- a write on a locked script
async def test_a_rewrite_lands_on_the_locked_script_and_retakes_only_that_line(mctx: Any) -> None:  # noqa: F811
    made = await tracked(mctx)                                   # every take ok, the mix submitted
    made.state = "cancelled"
    autolock.pending.clear()
    before = edited(mctx)["takes"]
    texts = []
    texts += said(await call(mctx, "event_change", {"id": "l1", "fields": {"words": "Line one, all of you."}}))
    assert not edited(mctx)["lock"]["locked"], "a write unlocks and locks nothing"
    got = await locks(mctx)
    texts += said(got)
    assert edited(mctx)["lock"]["locked"] is True and pressed_line(got).startswith("Script 1 · Track: 1 line")
    job = tracks(mctx)[-1]
    assert job.plan.summary["step_names"] == ["l1", "l1 · take 2", "l1 · take 3"]
    assert {k: v for k, v in edited(mctx)["takes"].items() if k != "l1"} == \
        {k: v for k, v in before.items() if k != "l1"}, "every other take record unchanged"
    job.state = "done"
    await run(mctx, job)
    mixing = mctx.jobs.made[-1]
    assert mixing.kind == "director.mix"
    await land(mctx, mixing)                                     # the mix after the re-take, written
    n = len(tracks(mctx))
    texts += said(await call(mctx, "event_move", {"id": "l2", "start_ms": edited_start(mctx, "l2") + 500}))
    got = await locks(mctx)
    assert len(tracks(mctx)) == n, "a move re-takes nothing"
    assert pressed_line(got) == f"Script 1 · Track: nothing to render; mixing (job {mctx.jobs.made[-1].id})", \
        "nothing to render: the mix again"
    for answer in (await call(mctx, "script_unlock", {}), await call(mctx, "line_add", HELLO),
                   await call(mctx, "script_read", {})):
        texts += said(answer)
    assert not edited(mctx)["lock"]["locked"]
    relock = await call(mctx, "script_lock", {})
    texts += said(relock)
    assert edited(mctx)["lock"]["locked"] is True and pressed_line(relock).startswith("Script 1 · Track: ")
    assert not any(w in t for t in texts for w in ("script_lock", "script_unlock", "wait", *WORDS)), texts


def mixes(ctx: Any) -> list[Any]:
    return [j for j in ctx.jobs.made if j.kind == "director.mix"]


# ---------------------------------------------------------------- a move during a mix
async def test_a_move_during_a_mix_presses_once_after_it(mctx: Any) -> None:  # noqa: F811
    first = await tracked(mctx)                                  # the mix queued
    autolock.pending.clear()
    await call(mctx, "event_move", {"id": "l2", "start_ms": edited_start(mctx, "l2") + 500})
    got = await autolock.start(mctx, "Script 1")
    assert got == f"Track: again when the mix (job {first.id}) ends"
    assert "Script 1" in autolock.pending and mixes(mctx) == [first]
    await land(mctx, first)
    assert edited(mctx).get("renders", {}).get("track") is None, "the stale mix not kept"
    [_, second] = mixes(mctx)
    assert not autolock.pending and autolock.said["Script 1"] == f"Track: nothing to render; mixing (job {second.id})"
    n = len(mctx.jobs.made)
    await land(mctx, second)
    assert edited(mctx)["renders"]["track"] == "Script 1.wav" and len(mctx.jobs.made) == n, "its finish presses nothing"


async def test_a_cancelled_mix_drops_pending(mctx: Any) -> None:  # noqa: F811
    first = await tracked(mctx)
    autolock.pending.clear()
    await call(mctx, "event_move", {"id": "l2", "start_ms": edited_start(mctx, "l2") + 500})
    await autolock.start(mctx, "Script 1")
    assert "Script 1" in autolock.pending
    first.state = "cancelled"
    await autolock.mix_ended(mctx, {"job": first.id, "kind": "director.mix", "state": "cancelled"})
    assert not autolock.pending and mixes(mctx) == [first] and "Script 1" not in mix.running


def edited_start(ctx: Any, ident: str) -> int:
    shot = next(s for s in edited(ctx)["scenes"][0]["shots"] if any(ev["id"] == ident for ev in s["events"]))
    return line(edited(ctx), ident)["start_ms"] - shot["start_ms"]


# ---------------------------------------------------------------- the audio panel
async def test_the_audio_panel_shows_for_every_written_script(mctx: Any) -> None:  # noqa: F811
    await whole(mctx)
    script = edited(mctx)
    del script["scenes"][0]["shots"][0]["camera"]["on"]
    put(mctx, script)
    got = routes._one(mctx, "Script 1")
    assert [r["id"] for r in got["audio"] if r["kind"] == "line"] == ["l1", "l2"] and not got["script"].get("lock")
    for shot in script["scenes"][0]["shots"]:
        shot["events"] = [ev for ev in shot["events"] if ev["kind"] not in ("line", "cue")]
    put(mctx, script)
    assert routes._one(mctx, "Script 1")["audio"] is None, "no line or cue: nothing to show"


# ---------------------------------------------------------------- the Track button
async def test_the_track_button_locks_any_written_script(mctx: Any) -> None:  # noqa: F811
    await whole(mctx)
    before = edited(mctx)
    line(before, "l2").pop("pace")
    put(mctx, before)
    assert not any("done" in sc for sc in before["scenes"])

    class Request:
        async def body(self) -> bytes:
            return b'{"name": "Script 1"}'
    got = await routes.post_track(mctx, Request())
    assert got["lines"] == 2 and len(tracks(mctx)) == 1
    after = edited(mctx)
    held = after.pop("lock")
    assert held["locked"] is True and isinstance(held["at"], str) and "T" in held["at"]
    line(before, "l2")["pace"] = line(after, "l2")["pace"]
    assert after == before, "nothing else changed but the mended voice field"


async def test_no_answer_names_a_lock_or_a_gap(mctx: Any) -> None:  # noqa: F811
    await whole(mctx)
    script = edited(mctx)
    del script["scenes"][0]["shots"][0]["camera"]["on"]
    put(mctx, script)
    texts = said(await call(mctx, "line_add", HELLO))
    texts += said(await call(mctx, "script_read", {}))
    texts += said(await call(mctx, "script_lock", {}))
    texts += said(await call(mctx, "script_unlock", {}))
    texts += said(await call(mctx, "scene_change", {"scene": 1, "done": True}))
    assert edited(mctx)["scenes"][0]["done"] is True
    with pytest.raises(Invalid) as e:
        await call(mctx, "script_track", {})              # busy: the first press's job runs
    texts += [e.value.text, *autolock.said.values()]
    assert not any(w in t for t in texts for w in WORDS), texts
