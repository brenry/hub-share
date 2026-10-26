"""The scene of `test_scene` with its takes (its fake ask). With the defaults each shot's
tasks are planned twice, take 2 on the next seed and named `… · take 2`; the cut reads each shot's best take; each
clip task carries the shot's spoken words for the words judge. The last step puts each shot's best take on track 1,
writes the scene's verdict line and each take's chip in the job's notes, and tells the redo record the take in the
cut and the takes that ran. With `scene_takes_max` 1 the plan is the golden `scene-plan.json`;
with `clip_judge` off nothing is heard and the judge step passes everything."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hub.modules.generate_image import redo
from tests.engine.test_judgeshot import judged
from tests.engine.test_scene import GOOD, beat, cast3, clips, plan, planned  # noqa: F401
from tests.engine.test_shotprompt import ctx, pick  # noqa: F401
from tests.engine.test_upstream_rules import REF2VA, cat  # noqa: F401

SILENT = plan(GOOD["shots"][0], beat("Character 6"), GOOD["shots"][2])


@pytest.fixture(autouse=True)
def fresh():
    redo.SCENES.clear()
    yield
    redo.SCENES.clear()


@pytest.fixture
def takes2(cast3):  # noqa: F811
    cast3.settings["scene_takes_max"] = 2                       # the default
    return cast3


async def test_each_shot_is_planned_twice_on_the_next_seed_and_cut_from_its_best(takes2):
    pick(takes2, REF2VA)
    job, _, _ = await planned(takes2, json.dumps(GOOD))
    p = job.plan
    assert [t["kind"] for t in p.tasks] == ["video"] * 6 + ["join"]
    assert p.takes == (((1,), (2,)), ((3,), (4,)), ((5,), (6,)))
    assert [t["seed"] for t in p.tasks[:6]] == [41, 42, 41, 42, 41, 42]
    assert p.summary["step_names"][:2] == ["Shot 1 · Character 7 · 6.6 s", "Shot 1 · Character 7 · 6.6 s · take 2"]
    assert len(p.summary["step_names"]) == len(p.tasks) and p.summary["shots"] == 3
    assert p.inputs[6] == {"items.0.path": (1, "best"), "items.1.path": (3, "best"), "items.2.path": (5, "best")}
    assert [t["words"] for t in p.tasks[:6:2]] == ["Line one, everybody.", "Thank you, friend. It is good to be "
                                                   "here.", "That is our scene."]
    assert p.tasks[0] == {**p.tasks[1], "seed": 41}, "a take is take 1's request on the next seed"
    assert p.judge is not None and p.finish.judge is p.judge and p.finish.job == job.id


async def test_a_shot_without_lines_is_not_heard(takes2):
    pick(takes2, REF2VA)
    job, _, _ = await planned(takes2, json.dumps(SILENT))
    assert [t["words"] for t in job.plan.tasks[:6]] == ["Line one, everybody."] * 2 + [None] * 2 + [
        "That is our scene."] * 2


async def test_finish_cuts_each_shots_best_take_and_writes_the_lines(takes2):
    pick(takes2, REF2VA)
    job, _, _ = await planned(takes2, json.dumps(GOOD))
    judge = job.plan.judge
    verdicts = {1: judged("Character 7"), 3: judged("Character 6", median=0.21, first=0.21, last=0.3, lost_at=0.0),
                4: judged("Character 6"), 5: judged("Character 7")}
    for task, verdict in verdicts.items():                     # as the dispatcher asks it on each task_done
        job.takes[task] = judge.done(task, {"task": task, "seconds": 60.0, "judge": verdict})
    made = clips(takes2, 5)
    landed = {1: made[0], 3: made[1], 4: made[2], 5: made[3], 7: made[4]}
    await job.plan.finish(landed)
    seq = takes2.files.sequence("Script 1")
    assert [i["clip"] for i in seq["tracks"][0]] == [made[0], made[2], made[3]], "shot 2's take 2 is in the cut"
    assert job.notes["verdict"] == ("Shot 1 take 1; shot 2 take 2 (take 1: Character 6's face 0.21); shot 3 take 1; "
                                    "re-takes used 1.0 of 15 min")
    assert job.notes["verdicts"][made[1]].startswith("Take 1 · not used · Character 6's face matched poorly")
    assert job.notes["verdicts"][made[2]].startswith("Take 2 · in the cut · Character 6's face held (0.44)")
    record = next(iter(redo.SCENES.values()))
    assert [s.clip for s in record.shots] == [made[0], made[2], made[3]]
    assert [s.takes for s in record.shots] == [1, 2, 1]


async def test_one_take_a_shot_is_the_golden_plan(takes2, tmp_path):
    takes2.settings["scene_takes_max"] = 1
    pick(takes2, REF2VA)
    job, _, _ = await planned(takes2, json.dumps(GOOD))
    p = job.plan
    text = json.dumps({"tasks": p.tasks, "inputs": [{k: list(v) for k, v in i.items()} for i in p.inputs],
                       "summary": p.summary, "takes": p.takes}, sort_keys=True, indent=1).replace(str(tmp_path), "TMP")
    assert text + "\n" == (Path(__file__).parents[1] / "fixtures" / "scene-plan.json").read_text(encoding="utf-8")


async def test_with_the_judges_off_nothing_is_heard_and_every_take_passes(takes2):
    takes2.settings["clip_judge"] = False
    pick(takes2, REF2VA)
    job, _, _ = await planned(takes2, json.dumps(GOOD))
    assert all(t["words"] is None and t["judge"] is None for t in job.plan.tasks[:6])
    take: Any = job.plan.judge.done(1, {"task": 1, "seconds": 60.0})
    assert take.passes and take.line == "Not judged: no judge ran"
