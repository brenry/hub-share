"""Every shot tells what happens in it, and a new story is written in two passes (`saystory.py`: pass 1 the
planner's shot list, checked and sent back; pass 2 the Hub's script exactly as written; `layout.py`, `scriptshape.py`,
`frame.py`, `sayask.py`, `say.py`, `landing.py`; `render.py`). End to end: a story message, a stub pass-1 answer of 6
shots with varied framings and the planner's own lengths, the script written exactly (lengths kept exactly), Render's
job plan with each shot's compiled prompt carrying its action. Sent back: a shot with no action, two neighbouring
shots of one framing, a short total (never stretched, never padded: at the last ask nothing is written). No code path
writes a seconds value the planner did not send. Render with a sketch panel in a shot. Neutral names only (CLAUDE.md).
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest

from hub.core.api import Invalid
from hub.modules.director import (
    frame,
    landing,
    length,
    render,
    routes,
    say,
    sayask,
    sayhold,
    saystory,
    scriptshape,
)
from tests.engine.helpers import FakeRequest
from tests.engine.test_script_held import CONTEXT, NAME, P1, P2, clean, told  # noqa: F401  (clean: the fixture)
from tests.engine.test_script_mix import mctx  # noqa: F401  (the fixture)
from tests.engine.test_script_render import CONTEXT as RCONTEXT
from tests.engine.test_script_render import (
    cat,  # noqa: F401  (the fixture)
    two_shots,
)
from tests.engine.test_script_render import ctx as rctx  # noqa: F401  (the fixture)
from tests.engine.test_script_tools import Model, on_disk
from tests.engine.test_script_track import ctx as track_ctx  # noqa: F401  (the fixture)

OWN = [4, 12, 6.5, 15, 8, 14.5]                                  # the planner's own seconds: 60 in all
FRAMINGS = ["Wide shot", "Medium shot", "Close-up", "Over-the-shoulder", "Insert", "Reaction"]
STORY = f"Scene 1 of {P1} and {P2}, 60 seconds, six shots."


def shots(seconds: list[float] | None = None, framings: list[str] | None = None, who: tuple[str, str] = (P1, P2),
          **more: Any) -> list[dict]:
    return [{"framing": f, "on": [who[k % 2]], "action": f"action {k + 1}", "seconds": s, "sound": "", **more}
            for k, (s, f) in enumerate(zip(seconds or OWN, framings or FRAMINGS, strict=True))]


def answer(listed: list[dict], title: str = NAME, seconds: int | None = 60) -> str:
    return json.dumps({"title": title, **({"seconds": seconds} if seconds else {}), "shots": listed})


def back(ctx: Any, k: int = 2) -> str:
    return str(ctx.model.sent[k][-1]["content"])


# ---------------------------------------------------------------- end to end: story -> script -> Render's job plan
async def test_a_story_is_written_exactly_and_each_shot_renders_its_action(rctx: Any) -> None:  # noqa: F811
    ctx, words = rctx, "Scene 1 of A and B, 60 seconds, six shots. Then render the video."
    listed = shots(who=("A", "B"))
    listed[0]["on"] = ["A", "B"]
    listed[1]["sound"] = "sound 1"
    listed[2]["lines"] = [{"speaker": "A", "words": "line 1"}]
    ctx.model = Model(json.dumps(RCONTEXT), answer(listed, "Script 2"))
    base = type(ctx).service

    def service(name: str) -> Any:
        if name == "ask":
            return ctx.model
        if name == "said":
            return lambda: {"id": "m1", "text": words, "first": True}
        return base(ctx, name)
    ctx.service = service
    got = await say.script_say(ctx, {"words": words})
    [line] = got["state"]
    assert line.startswith("Script 2: wrote 1 scene, 6 shots, 1 line, 1 cue · runs 60.0 s (60 s asked)"), line
    assert "rendering 6 shots" in line and "\n" not in line and line.count(". ") <= 1, "one line"
    assert len(ctx.model.sent) == 2, "the context, then one pass-1 ask"
    assert "operations" not in json.dumps(ctx.model.schemas[1]), "the model writes no tool operations"
    held = json.loads((routes.folder(ctx) / "Script 2.json").read_text(encoding="utf-8"))
    scene = held["scenes"][0]
    assert [s["seconds"] for s in scene["shots"]] == OWN, "the planner's own lengths, kept exactly"
    assert [s["action"] for s in scene["shots"]] == [f"action {k}" for k in range(1, 7)]
    assert [s["camera"]["framing"] for s in scene["shots"]] == FRAMINGS and scene["seconds"] == 60
    assert [s["camera"]["on"] for s in scene["shots"]][:2] == [["A", "B"], ["B"]]
    assert length.length(scene) == 60_000 and scene["done"] is True
    assert [(e["kind"], e.get("cue"), e["words"]) for e in scene["shots"][1]["events"] if e["kind"] == "cue"] == [
        ("cue", "effect", "sound 1")]
    tasks = ctx.jobs.get("j1").plan.tasks
    assert len(tasks) == 7, "six shots, then the join"
    for k, task in enumerate(tasks[:6], 1):
        assert f"action {k}." in task["prompt"], (k, task["prompt"])
        assert "No one speaks" not in task["prompt"], "no sentence of the Hub's"
        if k != 3:
            assert "<d>" not in task["prompt"], "no line: no dialogue"
    assert "<d>line 1</d>" in tasks[2]["prompt"], "a line that names no language: none in its <d>"


# ---------------------------------------------------------------- the checks, each sent back to pass 1
async def test_a_shot_with_no_action_is_sent_back(mctx: Any) -> None:  # noqa: F811
    bare = shots()
    bare[2]["action"] = " "
    bare[4].pop("action")
    await told(mctx, STORY, answer(bare), answer(shots()))
    assert "shots 3, 5 have no action: write what we see happen in it" in back(mctx)
    assert [s["action"] for s in on_disk(mctx, NAME)["scenes"][0]["shots"]] == [f"action {k}" for k in range(1, 7)]


async def test_neighbouring_shots_of_one_framing_are_sent_back(mctx: Any) -> None:  # noqa: F811
    same = shots(framings=[*FRAMINGS[:2], " medium  SHOT", *FRAMINGS[3:]])
    await told(mctx, STORY, answer(same), answer(shots()))
    assert "shots 2 and 3 have the same framing: neighbouring shots differ in framing" in back(mctx)
    assert len(mctx.model.sent) == 3
    assert [s["camera"]["framing"] for s in on_disk(mctx, NAME)["scenes"][0]["shots"]] == FRAMINGS


async def test_a_short_total_is_written_and_says_both_lengths(mctx: Any) -> None:  # noqa: F811
    short = [2, 3, 2, 3, 2, 3]
    line = await told(mctx, STORY, answer(shots(short)))
    assert len(mctx.model.sent) == 2, "the context, then one pass-1 ask: no send-back for a total"
    assert "runs 15.0 s (60 s asked)" in line, line
    scene = on_disk(mctx, NAME)["scenes"][0]
    assert [s["seconds"] for s in scene["shots"]] == short and scene["seconds"] == 60, "none stretched, none added"


async def test_seconds_past_one_window_are_sent_back_never_held_to_it(mctx: Any) -> None:  # noqa: F811
    await told(mctx, STORY, answer(shots([20, 12, 6.5, 15, 8, 0.5])), answer(shots()))
    assert "shot 1 has seconds a shot cannot hold (more than 0, up to 15 s" in back(mctx), back(mctx)
    assert [s["seconds"] for s in on_disk(mctx, NAME)["scenes"][0]["shots"]] == OWN


async def test_a_shot_held_half_a_second_is_written(mctx: Any) -> None:  # noqa: F811
    held = [12, 12, 6.5, 15, 8, 0.5]                                           # no least of 1 s
    await told(mctx, STORY, answer(shots(held)))
    assert len(mctx.model.sent) == 2, "the context, then one pass-1 ask"
    assert [s["seconds"] for s in on_disk(mctx, NAME)["scenes"][0]["shots"]] == held


async def test_no_length_named_keeps_the_planners_lengths_and_sets_none(mctx: Any) -> None:  # noqa: F811
    own = [3, 7.5, 2, 9, 4.5, 1]
    await told(mctx, f"Scene 1 of {P1} and {P2}, six shots.", answer(shots(own), seconds=None))
    scene = on_disk(mctx, NAME)["scenes"][0]
    assert [s["seconds"] for s in scene["shots"]] == own and "seconds" not in scene
    assert length.length(scene) == sum(own) * 1000


# ---------------------------------------------------------------- no seconds the planner did not send
def test_no_code_path_writes_a_seconds_value_the_planner_did_not_send() -> None:
    assert not hasattr(sayhold, "reach") and not hasattr(sayhold, "WIDE"), "no padding in sayhold"
    script = {"version": 2, "context": copy.deepcopy(CONTEXT), "scenes": [
        {"title": "Scene 1", "cast": [P1], "shots": [{"id": "s1", "start_ms": 0, "end_ms": 1000, "events": []}]}]}
    for op in ({"op": "add_shot", "framing": "Wide shot", "seconds": 20}, {"op": "add_shot", "framing": "Wide shot",
               "seconds": 0}, {"op": "change_shot", "shot": 1, "seconds": 2.55},
               {"op": "add_scene", "title": "Scene 2", "seconds": 59.5}, {"op": "set_length", "seconds": 0.5}):
        with pytest.raises(Invalid):
            sayask.calls(op, script, {})
    hints = {"problem": "Shot s1 past 15.00 s", "hints": {"shot": "s1", "max_seconds": 9.4}}
    assert landing.correction("event_change", {"id": "s1", "fields": {"seconds": 12}}, hints, script) is None
    root = Path(saystory.__file__).parent                     # where a shot's seconds are written: the planner's value
    written = {(p.name, m.group(0).strip()) for p in root.glob("*.py") for m in
               re.finditer(r'.*\["seconds"\]\s*=[^#\n]*', p.read_text(encoding="utf-8"))}
    assert written == {("frame.py", 'scene["seconds"] = args["seconds"]'), ("frame.py", 'shot["seconds"] = hold'),
                       ("layout.py", 'shot["seconds"] = seconds'),             # a scene's length,
                       ("owner.py", 'last["seconds"] = rest'),                  # as typed
                       ("saystory.py", 'value["seconds"] = round(n)')}, written


def test_pass_2_is_the_shot_list_as_written() -> None:
    listed = shots()
    listed[0]["on"] = [P1, "Subject 3"]
    listed[1]["sound"] = "sound 1"
    listed[1]["lines"] = [{"speaker": P2, "words": "line 1"}]
    ops = saystory.operations({"title": NAME, "seconds": 60, "shots": listed}, [P1, P2])
    assert ops[:2] == [{"op": "cast", "name": "Subject 3"},
                       {"op": "add_scene", "title": NAME, "cast": [P1, "Subject 3", P2], "seconds": 60}]
    assert [op["seconds"] for op in ops if op["op"] == "add_shot"] == OWN
    assert ops[3:6] == [{"op": "add_shot", "framing": "Medium shot", "on": [P2], "action": "action 2", "seconds": 12},
                        {"op": "add_line", "speaker": P2, "words": "line 1"},
                        {"op": "add_cue", "cue": "effect", "words": "sound 1"}]
    assert saystory.problems({"title": NAME, "shots": shots()}) == []
    assert saystory.problems({"title": NAME}) and saystory.problems(None)
    held = saystory.schema([P1, P2])
    assert held["properties"]["shots"]["items"]["required"] == ["framing", "on", "action", "seconds", "sound"]
    system = saystory.messages({"context": CONTEXT, "scenes": []}, STORY)[0]["content"]
    for rule in ("establish the place", "then go closer", "vary the framing", "cut on action", "pace each shot's "
                 "length by its moment", "build to a turn and an end"):
        assert rule in system, rule


# ---------------------------------------------------------------- the format and the frame
def one(*events: dict, **more: Any) -> dict:
    return {"version": 2, "context": copy.deepcopy(CONTEXT), "scenes": [{"title": "Scene 1", "cast": [P1, P2],
                                                                         "shots": [
        {"id": "s1", "start_ms": 0, "end_ms": 4_000, "camera": {"framing": "framing 1", "on": [P1]},
         "events": list(events), "seconds": 4, **more}]}]}


def test_a_shot_holds_its_action_and_a_change_changes_it() -> None:
    names = {P1.casefold(), P2.casefold()}
    scriptshape.read(one(action="action 1"), names)
    for bad in ("", " ", 3):
        with pytest.raises(Invalid):
            scriptshape.read(one(action=bad), names)
    assert len(scriptshape.read(one(action="x" * 20_001), names)["scenes"][0]["shots"][0]["action"]) == 20_001
    s, counters = one(), {"s": 1}
    s["scenes"][0]["shots"].clear()
    frame.shot_add(s, counters, {"scene": 1, "camera": {"framing": "framing 1"}, "seconds": 3, "action": "action 1"})
    shot = s["scenes"][0]["shots"][0]
    assert shot["action"] == "action 1" and shot["seconds"] == 3
    did = frame.change(s, {"id": shot["id"], "fields": {"action": "action 2", "seconds": 5}})
    assert shot["action"] == "action 2" and shot["end_ms"] - shot["start_ms"] == 5_000 and "its action" in did["did"]
    frame.change(s, {"id": shot["id"], "fields": {"action": ""}})     # an emptied action is taken off
    assert "action" not in shot
    scriptshape.read(s, names)


# ---------------------------------------------------------------- Render
def test_render_takes_the_shots_action_beside_a_sketch_panel() -> None:
    panel = {"id": "f1", "kind": "panel", "at_ms": 0, "picture": None, "stale": False}
    pose = {"id": "p1", "kind": "pose", "start_ms": 0, "end_ms": 4_000, "character": P1, "pose": "turn"}
    s = one(panel, pose, action="action 1")
    scene = s["scenes"][0]
    shot = scene["shots"][0]
    got = render.shot(s, scene, shot, render.who(scene, shot))
    assert got["action"] == ["action 1"] and got["lines"] == [], "the shot's action as its action; no line"
    shot.pop("action")
    assert render.shot(s, scene, shot, render.who(scene, shot))["action"] == [], "no action made up"


async def test_render_presses_with_a_sketch_panel_in_a_shot(rctx: Any) -> None:  # noqa: F811
    ctx = rctx
    await two_shots(ctx)
    path = routes.folder(ctx) / "Script 1.json"
    body = json.loads(path.read_text(encoding="utf-8"))
    body["scenes"][0]["shots"][1]["events"].append({"id": "f1", "kind": "panel", "at_ms": body["scenes"][0]["shots"][
        1]["start_ms"], "picture": None, "stale": False})
    body["scenes"][0]["shots"][1]["action"] = "action 2"
    path.write_text(json.dumps(body), encoding="utf-8")
    got = await routes.post_render(ctx, FakeRequest(body=json.dumps({"name": "Script 1"}).encode()))
    assert got == {"job": "j1", "shots": 2, "skipped": []}, got
    assert "action 2." in ctx.jobs.get("j1").plan.tasks[1]["prompt"]
