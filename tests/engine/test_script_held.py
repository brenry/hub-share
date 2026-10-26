"""Held shots (`layout.hold_ms`, `timing.py`, `air.py`, `frame.py`, `scriptshape.py`; the planner's
`sayask.py`, `saycheck.py`, `sayhold.py`, `saytrial.py`, `sayline.py`, `say.py`; `render.py`). On stub planner
answers: a 60 s scene of held shots with no line is written and done (the Hub's own held shots are gone,
`test_script_action.py`); a message that asks to write and then render presses Render; the answer is one short line
with no `not done:` and no request for words. Pure: an old file without `seconds` times as before; the empty-shot and
dead-air rules hold for an unheld shot; Render plans a held shot at its held length with no line. Neutral names only
(CLAUDE.md)."""
from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from typing import Any

import pytest

from hub.core.api import Invalid
from hub.modules.director import (
    air,
    autolock,
    frame,
    layout,
    length,
    mix,
    render,
    say,
    sayhold,
    sayline,
    saytrial,
    scriptshape,
    timing,
)
from hub.modules.director import routes as droutes
from tests.engine.helpers import FakeRequest
from tests.engine.test_media_characters import png_bytes
from tests.engine.test_script_mix import mctx  # noqa: F401  (the fixture)
from tests.engine.test_script_render import NAME as RNAME
from tests.engine.test_script_render import cat  # noqa: F401  (the fixture)
from tests.engine.test_script_render import ctx as rctx  # noqa: F401  (the fixture)
from tests.engine.test_script_render import edit as redit
from tests.engine.test_script_say import hub, lines, shot_list
from tests.engine.test_script_tools import Model, on_disk
from tests.engine.test_script_track import call
from tests.engine.test_script_track import ctx as track_ctx  # noqa: F401  (the fixture)

P1, P2, NAME = "Subject 1", "Subject 2", "Script 1"
CONTEXT = {"cast": [{"name": P1, "look": "look 1", "costume": "wardrobe 1", "home": 30},
                  {"name": P2, "look": "look 2", "costume": "wardrobe 2", "home": 70}],
         "set": {"name": "set 1", "description": "set 1 of Scene 1", "elements": ["prop 1"], "props": []},
         "style": "style 1"}
STORY = f"Scene 1 of {P1} and {P2}, 60 seconds, no line spoken, cut between many framings."
HELD = [{"op": "add_scene", "title": "Scene 1", "cast": [P1, P2], "seconds": 60},
        *[op for k in range(1, 7) for op in (
            {"op": "add_shot", "framing": f"framing {k}", "on": [P1, P2][: 1 + k % 2], "seconds": 10,
             "action": f"action {k}"},
            *([{"op": "add_cue", "cue": "effect", "words": "cue 1"}] if k == 3 else []))]]


@pytest.fixture(autouse=True)
def clean() -> Iterator[None]:
    for held in (autolock.said, autolock.pending, mix.running, mix.failed, say.handled, say.tasks):
        held.clear()
    yield
    for held in (autolock.said, autolock.pending, mix.running, mix.failed, say.handled, say.tasks):
        held.clear()


def plan(ops: list[dict]) -> str:
    """A new story's pass-1 answer, the shot list of `ops`' shots, lines and cues."""
    return shot_list(ops, NAME)


async def told(ctx: Any, words: str, *replies: str) -> str:
    (ctx.files.roots["chars"] / f"{P1}.png").write_bytes(png_bytes())
    ctx.model = Model(json.dumps(CONTEXT), *replies)
    hub(ctx, words, "m1", first=True)
    got = await call(ctx, "script_say", {"words": words})
    hub(ctx, None)
    return got["state"][0]


def plain_line(line: str) -> None:
    assert "not done" not in line and "words" not in line and "(" not in line.split("asked)")[-1], line


# ---------------------------------------------------------------- the planner
async def test_a_60_s_scene_of_held_shots_with_no_line_is_written_and_done(mctx: Any) -> None:  # noqa: F811
    line = await told(mctx, STORY, plan(HELD))
    assert line == f"{NAME}: wrote 1 scene, 6 shots, 1 cue · runs 60.0 s (60 s asked)", line
    held = on_disk(mctx, NAME)
    scene = held["scenes"][0]
    assert [s["seconds"] for s in scene["shots"]] == [10] * 6 and length.length(scene) == 60_000
    assert scene["done"] is True and lines(held) == [] and air.dead(scene) == 0
    assert [s["action"] for s in scene["shots"]] == [f"action {k}" for k in range(1, 7)]
    assert len(mctx.model.sent) == 2, "one ask: nothing sent back"
    system = mctx.model.sent[1][0]["content"]
    assert "how long the shot is held" in system and "never an equal share" in system


async def test_write_then_render_presses_render_in_the_same_answer(mctx: Any, monkeypatch: Any) -> None:  # noqa: F811
    pressed: list[str] = []
    monkeypatch.setattr(render, "press", lambda ctx, name: pressed.append(name) or {"job": "j1", "shots": 6,
                                                                                    "skipped": []})
    line = await told(mctx, f"{STORY} Then render the video.", plan(HELD))
    assert pressed == [NAME] and on_disk(mctx, NAME)["scenes"][0]["done"] is True
    assert line == f"{NAME}: wrote 1 scene, 6 shots, 1 cue · runs 60.0 s (60 s asked) · rendering 6 shots"


async def test_no_render_word_presses_nothing(mctx: Any, monkeypatch: Any) -> None:  # noqa: F811
    monkeypatch.setattr(render, "press", lambda ctx, name: pytest.fail("pressed"))
    assert "rendering" not in await told(mctx, STORY, plan(HELD))
    assert sayhold.wants_render("Write it, then produce the video.") and sayhold.wants_render("render it")
    assert not sayhold.wants_render(STORY) and not sayhold.wants_render("make a video of Scene 1")


def test_the_short_answer_is_one_line_and_one_sentence() -> None:
    tried = saytrial.Tried({"version": 2, "context": CONTEXT, "scenes": [
        {"title": "Scene 1", "cast": [P1], "seconds": 60, "shots": []}]}, True)
    tried.kept = ["scene 1: Scene 1 has no shot, so nothing to time (Add a shot to scene 1 first: shot_add)"]
    line = sayline.line(tried, None, None)
    assert line == "wrote 1 scene · runs 0.0 s (60 s asked). Scene 1 has no shot, so nothing to time.", line
    plain_line(line)
    assert line.count(". ") == 1 and line.endswith(".")


# ---------------------------------------------------------------- the format and the timing
def script(*shots: dict) -> dict:
    return {"version": 2, "context": copy.deepcopy(CONTEXT), "scenes": [
        {"title": "Scene 1", "cast": [P1, P2], "shots": list(shots)}]}


def shot(ident: str, start: int, end: int, *events: dict, **more: Any) -> dict:
    return {"id": ident, "start_ms": start, "end_ms": end, "camera": {"framing": "framing 1"}, "events": list(events),
            **more}


def cue(ident: str, start: int, end: int) -> dict:
    return {"id": ident, "kind": "cue", "start_ms": start, "end_ms": end, "cue": "effect", "words": "cue 1"}


def test_an_old_file_without_seconds_times_as_before() -> None:
    old = script(shot("s1", 0, 2_000, cue("c1", 0, 2_000)), shot("s2", 2_000, 3_000))
    scriptshape.read(old, {P1.casefold(), P2.casefold()})
    after = copy.deepcopy(old)
    timing.retime(copy.deepcopy(old), after)
    assert after == old, "nothing moves"
    assert air.empty(old["scenes"][0]["shots"][1]) and air.unfilled(old, 1)[0].startswith("s2: nothing in it")


def test_dead_air_and_empty_shots_hold_for_an_unheld_shot_only() -> None:
    gap = script(shot("s1", 0, 6_000, cue("c1", 0, 2_000), cue("c2", 4_000, 6_000)))
    assert air.dead(gap["scenes"][0]) == 2_000 and air.unfilled(gap, 1)
    held = copy.deepcopy(gap)
    held["scenes"][0]["shots"][0]["seconds"] = 6
    assert air.dead(held["scenes"][0]) == 0 and air.unfilled(held, 1) == []
    assert air.holes(held["scenes"][0]["shots"][0]) == []
    alone = shot("s1", 0, 1_000, seconds=1)
    assert not air.empty(alone) and air.bare(alone)


def test_a_held_shot_runs_its_hold_or_what_its_events_need() -> None:
    s, counters = script(), {}
    frame.shot_add(s, counters, {"scene": 1, "camera": {"framing": "framing 1"}})
    did = frame.shot_add(s, counters, {"scene": 1, "camera": {"framing": "framing 2"}, "seconds": 12.5})
    assert did["did"].endswith("holds 12.5 s")
    first, second = s["scenes"][0]["shots"]
    assert (first["end_ms"], second["start_ms"], second["end_ms"]) == (1_000, 1_000, 13_500)
    second["events"].append(cue("c1", 1_000, 15_000))
    timing.retime(copy.deepcopy(s), s)
    assert second["end_ms"] == 15_000, "its events need more than its hold"
    second["events"].clear()
    timing.retime(copy.deepcopy(s), s)
    assert second["end_ms"] == 13_500, "its hold again"
    frame.change(s, {"id": second["id"], "fields": {"seconds": 0}})
    assert "seconds" not in second and second["end_ms"] == 2_000, "no hold: an empty shot's second"
    frame.change(s, {"id": second["id"], "fields": {"seconds": 4}})
    assert second["end_ms"] - second["start_ms"] == 4_000
    with pytest.raises(Invalid):
        frame.change(s, {"id": second["id"], "fields": {"seconds": 15.5}})
    scriptshape.read(s, {P1.casefold(), P2.casefold()})


def test_the_format_takes_seconds_on_a_shot() -> None:
    names = {P1.casefold(), P2.casefold()}
    for good in (0.1, 0.5, 1, 15, 15.0, 2.5):                       # no least of the Hub's
        scriptshape.read(script(shot("s1", 0, 15_000, seconds=good)), names)
    for bad in (0, -1, 15.1, 2.55, "2", True):
        with pytest.raises(Invalid):
            scriptshape.read(script(shot("s1", 0, 15_000, seconds=bad)), names)
    assert layout.hold_ms({"seconds": 2.5}) == 2_500 and layout.hold_ms({}) == 0


# ---------------------------------------------------------------- Render
async def test_render_renders_a_held_shot_for_its_held_length(rctx: Any) -> None:  # noqa: F811
    ctx = rctx
    from hub.modules.director import tools

    await tools._write(ctx, lambda s, c, ch: frame.scene_add(s, {"title": "Scene 1", "cast": ["A", "B"]}), None,
                       RNAME)
    got = await redit(ctx, "add_shot", scene=1, camera={"framing": "framing 1", "move": "move 1"}, seconds=12)
    assert "problem" not in got, got
    made = await droutes.post_render(ctx, FakeRequest(body=json.dumps({"name": RNAME}).encode()))
    assert made["shots"] == 1
    plan_ = ctx.jobs.get(made["job"]).plan
    task = plan_.tasks[-2]
    assert "<d>" not in task["prompt"] and "No one speaks" not in task["prompt"], "no line: no <d>, no guard"
    assert abs(plan_.summary["seconds"] - 12) < 0.5, "its held 12 s on the model's frame lattice"
