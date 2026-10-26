"""Redo one shot of a scene, with a fake ask and the worker's own catalog for upstream's H3 capture. The
scene's plan is kept in memory (`redo.SCENES`) from its planning; `redo_shot {shot}` queues one job whose planning
step sends the kept shot's tasks on the kept seed + its takes (prompt, frames, pictures as the scene's), then the
scene's cut with every other shot's landed file and the reactions where they were. Its finish puts the new take where
the old was in the scene's sequence, its in/out kept, track 2 as it was. What it cannot do fails at planning in
one line, nothing asked of the engine. Nothing reaches disk but the sequence."""
from __future__ import annotations

import json
from typing import Any

import pytest

from hub.core import dispatch, enginelane
from hub.core.api import Invalid
from hub.modules.generate_image import redo, screen
from tests.engine.test_generate_image import call
from tests.engine.test_scene import GOOD, cast3, clips, plan, planned  # noqa: F401
from tests.engine.test_scene_audience import keep
from tests.engine.test_shotprompt import ctx, pick  # noqa: F401
from tests.engine.test_upstream_rules import FL2VA, REF2VA, cat  # noqa: F401

TITLE = "Script 1"
REACTING = plan({**GOOD["shots"][0], "reaction": "applause"}, *GOOD["shots"][1:])


@pytest.fixture(autouse=True)
def fresh():
    redo.SCENES.clear()
    yield
    redo.SCENES.clear()


async def scene_made(c: Any, made: int = 3) -> tuple[Any, list[str]]:
    """The scene planned, its first `made` shots and (all made) its cut landed, its finish run."""
    pick(c, REF2VA)
    keep(c, "applause")
    job, _, _ = await planned(c, json.dumps(REACTING))
    files = clips(c, made + 1)
    landed = dict(enumerate(files[:made], 1)) | ({4: files[3]} if made == 3 else {})
    await job.plan.finish(landed)
    return job, files[:made]


async def redone(c: Any, args: dict) -> tuple[Any, list[str]]:
    """`redo_shot` then the job's planning step, as the dispatcher runs it: -> (the job, the lines)."""
    lines: list[str] = []
    before = set(c.jobs.jobs)
    answer = await call(c, "redo_shot", args)
    [key] = set(c.jobs.jobs) - before
    job, params = c.jobs.jobs[key]
    assert answer == {"state": "queued", "job": job.id} and params == {"redo": {"shot": args["shot"],
                                                                                "scene": args.get("scene")}}
    assert job.plan.tasks == () and job.plan.prepare.job == job.id
    queued = job.plan
    job.plan = await job.plan.prepare(lines.append)
    dispatch.checked(queued, job.plan)                                 # as the dispatcher holds a plan it planned
    enginelane.checked(job)                                            # every task one the worker parses
    return job, lines


def _clip(c: Any, name: str) -> str:
    from tests.fakes.mp4 import tiny_mp4
    folder = c.files.roots["clips"] / "2026-10-18"
    (folder / f"{name}.mp4").write_bytes(tiny_mp4(audio=True))
    return f"clips/2026-10-18/{name}.mp4"


async def test_the_scene_is_kept_and_redo_shot_2_sends_its_tasks_on_the_next_seed(cast3):  # noqa: F811
    scene, shots = await scene_made(cast3)
    [record] = redo.SCENES.values()
    assert (record.name, record.ended, [s.clip for s in record.shots]) == (TITLE, True, shots)
    job, lines = await redone(cast3, {"shot": 2})
    p, was = job.plan, scene.plan.tasks
    assert lines == ["Redo · shot 2 of Script 1"]
    assert [t["kind"] for t in p.tasks] == ["video", "join"] and p.model == REF2VA
    assert p.tasks[0] == {**was[1], "seed": was[1]["seed"] + 1}, "the same shot plan, a new seed"
    cut = p.tasks[1]
    paths = [str(cast3.files.resolve(s)) for s in shots]
    assert [i["path"] for i in cut["items"]] == [paths[0], "", paths[2]]
    assert [{**i, "path": ""} for i in cut["items"]] == was[3]["items"], "the scene's frames"
    assert cut["audio"] == was[3]["audio"] and cut["canvas"] == was[3]["canvas"], "the reactions where they were"
    assert p.inputs == ({}, {"items.1.path": (1, "kept")})
    names = p.summary["step_names"]
    assert names[0] == scene.plan.summary["step_names"][1] + " · take 2" \
        and names[0].startswith("Shot 2 · Character 6 · ")
    assert names[1:] == ["Cut · 1 reaction"]
    assert (p.summary["mode"], p.summary["shots"], p.summary["prompt"]) == ("scene", 3, "Redo shot 2 of Script 1")
    assert p.summary["seeds"] == [was[1]["seed"] + 1] and p.prepare is None


async def test_redo_finish_swaps_only_shot_2_and_keeps_the_users_trim(cast3):  # noqa: F811
    _, shots = await scene_made(cast3)
    seq = cast3.files.sequence(TITLE)
    one, two = seq["tracks"]
    one[1] = {**one[1], "in": 10, "out": 100}                          # shot 2 trimmed on Edit Video
    cast3.files.sequence_save(TITLE, [one, two], seq["revision"], 8)
    before = cast3.files.sequence(TITLE)
    job, _ = await redone(cast3, {"shot": 2, "scene": "SCRIPT 1"})
    take, new_cut = _clip(cast3, "take-2"), _clip(cast3, "cut-2")
    await job.plan.finish({1: take, 2: new_cut})
    after = cast3.files.sequence(TITLE)
    assert after["tracks"][0] == [before["tracks"][0][0], {"clip": take, "in": 10, "out": 100},
                                  before["tracks"][0][2]]
    assert after["tracks"][1] == before["tracks"][1] and after["revision"] == before["revision"] + 1
    assert cast3.events[-1] == ("sequence.written", {"name": TITLE, "revision": after["revision"]})
    assert all(cast3.files.clip_facts(c) for c in shots), "nothing erased"
    again, _ = await redone(cast3, {"shot": 2})
    first = job.plan.tasks[0]["seed"]
    assert again.plan.tasks[0]["seed"] == first + 1 and again.plan.summary["step_names"][0].endswith(" · take 3")
    assert again.plan.tasks[1]["items"][1]["path"] == "" and again.plan.tasks[1]["items"][0]["path"] == str(
        cast3.files.resolve(shots[0]))


async def test_a_scene_stopped_after_shot_1_renders_shots_2_and_3(cast3):  # noqa: F811
    scene, shots = await scene_made(cast3, made=1)
    job, _ = await redone(cast3, {"shot": 2})
    p, was = job.plan, scene.plan.tasks
    assert [t["kind"] for t in p.tasks] == ["video", "video", "join"]
    assert p.tasks[:2] == was[1:3], "shots never made: their first take, on their own seeds"
    assert p.inputs[2] == {"items.1.path": (1, "kept"), "items.2.path": (2, "kept")}
    assert p.summary["step_names"] == scene.plan.summary["step_names"][1:]
    two, three, cut = _clip(cast3, "t2"), _clip(cast3, "t3"), _clip(cast3, "c")
    await p.finish({1: two, 2: three, 3: cut})
    assert [i["clip"] for i in cast3.files.sequence(TITLE)["tracks"][0]] == [shots[0], two, three]


async def test_a_redo_that_did_not_cut_leaves_the_sequence_as_it_was(cast3):  # noqa: F811
    await scene_made(cast3)
    before = cast3.files.sequence(TITLE)
    job, _ = await redone(cast3, {"shot": 2})
    await job.plan.finish({1: _clip(cast3, "take-2")})                  # the cut failed: the take is in Clips
    assert cast3.files.sequence(TITLE) == before
    again, _ = await redone(cast3, {"shot": 2})
    assert again.plan.tasks[0]["seed"] == job.plan.tasks[0]["seed"] + 1, "the take that landed counts"


async def refused(c: Any, args: dict) -> str:
    planned_before = len(c.engine.planned)
    with pytest.raises(Invalid) as err:
        await redone(c, args)
    assert len(c.engine.planned) == planned_before, "nothing asked of the engine"
    return err.value.text


async def test_no_scene_and_an_unknown_title(cast3):  # noqa: F811
    pick(cast3, REF2VA)
    assert await refused(cast3, {"shot": 2}) == "No scene was made since the Hub last started."
    cast3.jobs.jobs.clear()
    await scene_made(cast3)
    assert await refused(cast3, {"shot": 2, "scene": "Other scene"}) == (
        "Other scene was made before the Hub last started; a scene's plan is held in memory only. "
        "Send the scene again.")


async def test_each_line_the_hub_cannot_redo(cast3):  # noqa: F811
    _, shots = await scene_made(cast3)
    assert await refused(cast3, {"shot": 4}) == "Script 1 has 3 shots"
    pick(cast3, FL2VA)
    assert (await refused(cast3, {"shot": 2})).startswith("Script 1 was made on ")
    assert (await refused(cast3, {"shot": 2})).endswith("; pick it in Generate to redo its shot")
    pick(cast3, REF2VA)
    (cast3.files.roots["sounds"] / "audience" / "applause.wav").unlink()
    assert await refused(cast3, {"shot": 2}) == ("Audience: the applause sound of Script 1 is no longer in "
                                                 "Sounds; send the scene again")
    keep(cast3, "applause")
    cast3.files.resolve(shots[0]).unlink()
    assert await refused(cast3, {"shot": 2}) == "shot 1 of Script 1 is no longer in Clips; redo it too"
    cast3.files.sequence_delete(TITLE)
    assert await refused(cast3, {"shot": 1}) == "Script 1's sequence is no longer on Edit Video"


async def test_no_shot_made_and_a_ninth_scene_drops_the_first(cast3):  # noqa: F811
    await scene_made(cast3, made=0)
    assert await refused(cast3, {"shot": 1}) == "No shot of Script 1 was made; send the scene again"
    first = next(iter(redo.SCENES.values()))
    for _ in range(redo.KEPT):
        redo.keep(first.__class__(**{**first.__dict__, "shots": []}))
    assert len(redo.SCENES) == redo.KEPT and first not in redo.SCENES.values()


async def test_nothing_reaches_disk_but_the_sequence_and_the_screen_is_untouched(cast3, tmp_path):  # noqa: F811
    await scene_made(cast3)
    shown = screen.read(cast3)
    files = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    job, _ = await redone(cast3, {"shot": 2})
    await job.plan.finish({1: _clip(cast3, "take-2"), 2: _clip(cast3, "cut-2")})
    assert screen.read(cast3) == shown, "a redo writes nothing to the Generate screen"
    changed = {p for p in tmp_path.rglob("*") if p.is_file() and files.get(p) != p.read_bytes()}
    assert {p.name for p in changed if "sequences" in p.parts} == {"Script 1.json"}
    assert {p.parent.name for p in changed if "sequences" not in p.parts} == {"2026-10-18"}, "the take and the cut"
    words = ("Line one", "good to be here", "grey suit", "red dress", "Redo")
    for path in changed:
        assert not any(w.encode() in path.read_bytes() for w in words), path


async def test_a_redo_after_two_takes_sends_seed_plus_2_and_swaps_in_a_take_under_the_bar(cast3):  # noqa: F811
    """The redo's seed passes every take the scene ran; it plans one take and no re-take, and the new
    take goes in whatever it scored, with its chip."""
    from tests.engine.test_judgeshot import judged
    cast3.settings["scene_takes_max"] = 2
    pick(cast3, REF2VA)
    keep(cast3, "applause")
    scene, _, _ = await planned(cast3, json.dumps(REACTING))
    judge = scene.plan.judge
    for task, verdict in {1: judged("Character 7"), 3: judged("Character 6", median=0.1), 4: judged("Character 6",
                                                                                                    median=0.2),
                          5: judged("Character 7")}.items():
        scene.takes[task] = judge.done(task, {"task": task, "seconds": 60.0, "judge": verdict})
    made = clips(cast3, 5)
    await scene.plan.finish({1: made[0], 3: made[1], 4: made[2], 5: made[3], 7: made[4]})
    assert [s.takes for s in next(iter(redo.SCENES.values())).shots] == [1, 2, 1]
    job, _ = await redone(cast3, {"shot": 2})
    p, seed = job.plan, scene.plan.tasks[2]["seed"]
    assert p.tasks[0]["seed"] == seed + 2 and p.summary["step_names"][0].endswith(" · take 3")
    assert p.takes == (((1,),),) and not p.judge.again(1, 2), "no re-take of a redo"
    take = p.judge.done(1, {"task": 1, "seconds": 60.0, "judge": judged("Character 6", median=0.15)})
    job.takes[1] = take
    assert not take.passes
    new, cut = _clip(cast3, "take-3"), _clip(cast3, "cut-3")
    await p.finish({1: new, 2: cut})
    assert [i["clip"] for i in cast3.files.sequence(TITLE)["tracks"][0]] == [made[0], new, made[3]]
    assert job.notes["verdicts"][new].startswith("Take 3 · in the cut · Character 6's face scored 0.15")
    assert job.notes["verdict"].startswith("Shot 2 take 3, under the bar: Character 6's face scored 0.15")


async def test_redo_names_a_shot_by_its_number(cast3):  # noqa: F811
    await scene_made(cast3)
    assert await refused(cast3, {"shot": 9}) == f"{TITLE} has 3 shots", "refused by the scene, not job"
    with pytest.raises(Invalid) as err:
        redo.job({"redo": {"shot": 0}}, cast3)
    assert err.value.text == redo.ARGS == "Name a shot by its number"
