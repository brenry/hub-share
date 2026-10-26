"""A Generate press's takes inside its own job. A clip press with the defaults is two takes on seeds
s and s + 1 (`Render`, `Render · take 2`), take 1 the press's task plus the judge-only `words`; a convert clip is
`Render, Voice, Render · take 2, Voice · take 2` with its `inputs` shifted; a continue two takes; a line three takes
of one task. The judge off: the plan byte for byte. Count 1 with the judge on: one take, a judge, a finish. `words`
from the session's shot, from `<d>[English] …</d>`, none. A picture press untouched. `Finish` notes `best`,
`verdict` and `verdicts` for two takes, one line only when take 1 passed."""
from __future__ import annotations

import copy
from typing import Any

from hub.core.api import JobPlan
from hub.modules.generate_image import build, judgeshot, presstakes, routes
from tests.engine.test_clipconvert import character_7_alone, press
from tests.engine.test_generate_image import call
from tests.engine.test_shotprompt import CHARACTER_7, LINE, ctx, pick  # noqa: F401
from tests.engine.test_upstream_rules import REF2VA, cat  # noqa: F401
from tests.engine.test_voice_reference import sample

FACE = {"min": 0.44, "median": 0.44, "first": 0.44, "last": 0.44, "drift": 0.0, "lost_at": None, "present": 1.0}
POOR = {**FACE, "min": 0.21, "median": 0.21, "first": 0.21, "last": 0.21}


def reading(face: dict, heard: float = 1.0) -> dict:
    return {"face": {"Character 7": face}, "mouth": {"speaker": "Character 7", "lips": 0.71, "moving": 0.6},
            "words": {"heard": heard, "first_miss": None}}


def continue_plan() -> JobPlan:
    task = {"kind": "video", "model": REF2VA, "prompt": "x", "seed": 7, "judge": "cpu"}
    return JobPlan("image", REF2VA, (task,), {"kind": "clip", "mode": "continue", "prompt": "x", "seeds": [7]})


def line_plan(seed: int = 7) -> JobPlan:
    task = {"kind": "speech", "model": "tts", "prompt": "Stay right there!", "seed": seed, "judge": True}
    return JobPlan("image", "tts", (task,), {"kind": "sound", "prompt": "Stay right there!", "seeds": [seed]})


async def test_a_clip_press_with_the_defaults_is_two_takes(ctx):  # noqa: F811
    pick(ctx, REF2VA, CHARACTER_7)
    job = await press(ctx, character_7_alone())                     # no sample: one render
    plan = presstakes.plan(ctx, job.plan)
    s = job.plan.tasks[0]["seed"]
    assert [t["seed"] for t in plan.tasks] == [s, s + 1] and plan.summary["seeds"] == [s]
    assert plan.tasks[0] == {**job.plan.tasks[0], "words": LINE}, "take 1: the press plus `words`"
    assert plan.tasks[1] == {**job.plan.tasks[0], "words": LINE, "seed": s + 1}
    assert plan.summary["step_names"] == ["Render", "Render · take 2"] and plan.takes == (((1,), (2,)),)
    assert isinstance(plan.judge, judgeshot.ShotJudge) and isinstance(plan.finish, presstakes.Finish)
    assert plan.judge.cap == 15 * 60 and plan.judge.shots[0] == routes.session_part(ctx)["shot"]
    assert plan.inputs == () and plan.model == job.plan.model


async def test_a_convert_clip_is_its_two_steps_per_take(ctx):  # noqa: F811
    sample(ctx, "Character 7")
    pick(ctx, REF2VA, CHARACTER_7)
    job = await press(ctx, character_7_alone())
    plan = presstakes.plan(ctx, job.plan)
    assert plan.summary["step_names"] == ["Render", "Voice", "Render · take 2", "Voice · take 2"]
    assert plan.inputs == ({}, {"clip": (1, "file")}, {}, {"clip": (3, "file")}) and plan.takes == (((1, 2), (3, 4)),)
    assert [t["kind"] for t in plan.tasks] == ["video", "voice", "video", "voice"]
    assert plan.tasks[2]["seed"] == plan.tasks[0]["seed"] + 1 and plan.tasks[3] == plan.tasks[1], "the voice as sent"


def test_a_continue_is_two_takes_and_a_line_three(ctx):  # noqa: F811
    plan = presstakes.plan(ctx, continue_plan())
    assert [t["seed"] for t in plan.tasks] == [7, 8] and plan.summary["step_names"] == ["Render", "Render · take 2"]
    line = presstakes.plan(ctx, line_plan())
    assert [t["seed"] for t in line.tasks] == [7, 8, 9] and line.takes == (((1,), (2,), (3,)),)
    assert line.summary["step_names"] == ["Line", "Line · take 2", "Line · take 3"] and line.summary["seeds"] == [7]
    assert isinstance(line.judge, judgeshot.LineJudge) and "words" not in line.tasks[0]


async def test_the_judges_off_leave_the_plan_byte_for_byte(ctx):  # noqa: F811
    pick(ctx, REF2VA, CHARACTER_7)
    ctx.settings = {**ctx.settings, "clip_judge": False}
    job = await press(ctx, character_7_alone())
    assert presstakes.plan(ctx, job.plan) is job.plan
    ctx.settings = {**ctx.settings, "speech_judge": False}
    one = line_plan()
    assert presstakes.plan(ctx, one) is one


def test_count_1_with_the_judge_on_is_one_take_a_judge_and_a_finish(ctx):  # noqa: F811
    ctx.settings = {**ctx.settings, "scene_takes_max": 1, "speech_takes_max": 1}
    plan = presstakes.plan(ctx, continue_plan())
    assert len(plan.tasks) == 1 and plan.takes == (((1,),),) and plan.judge and plan.finish
    assert "step_names" not in plan.summary, "one take: the card as today"
    line = presstakes.plan(ctx, line_plan())
    assert len(line.tasks) == 1 and line.judge and line.finish


def test_words_from_the_shot_from_the_prompt_or_none(ctx):  # noqa: F811
    routes.session_part(ctx)["shot"] = {"lines": [{"speaker": "Character 7", "words": " Hello  there. "},
                                                  {"speaker": "Character 7", "words": "Bye."}]}
    assert presstakes.words(ctx, "<d>[English] ignored</d>") == "Hello there. Bye."
    routes.session_part(ctx).pop("shot")
    said = "Speaker 1 says <d>[English] Line one.</d> then <d>Bye now.</d>"
    assert presstakes.words(ctx, said) == "Line one. Bye now."
    assert presstakes.words(ctx, "Waves on a beach.") is None


def test_a_picture_press_and_a_planned_request_are_untouched(ctx, monkeypatch):  # noqa: F811
    picture = JobPlan("image", "flux", ({"kind": "image", "seed": 1},), {"prompt": "x", "seeds": [1]})
    assert presstakes.plan(ctx, picture) is picture
    planned = JobPlan("image", REF2VA, (), {"kind": "clip"}, prepare=lambda say: None)
    monkeypatch.setattr(build, "image_job", lambda p, c: planned)
    for key in ("direct", "scene", "redo"):
        assert presstakes.job({key: "x"}, ctx) is planned


def notes_of(plan: JobPlan, readings: dict[int, dict], landed: dict[int, str]) -> dict[str, Any]:
    for task, judged in readings.items():
        plan.judge.done(task, {"judge": judged, "seconds": 96.0})
    return plan.finish.notes(landed, plan.judge.seen)


def test_finish_marks_take_2_best_with_each_takes_chip(ctx):  # noqa: F811
    plan = presstakes.plan(ctx, continue_plan())
    plan.judge.shots[0] = {"lines": [{"speaker": "Character 7", "words": LINE}], "camera": {"framing": None}}
    notes = notes_of(plan, {1: reading(POOR), 2: reading(FACE)}, {1: "clips/a.mp4", 2: "clips/b.mp4"})
    held = "Character 7's face held (0.44); Character 7's mouth moves with the words (0.71); heard 100% of the words"
    assert notes["best"] == "clips/b.mp4" and notes["best_task"] == 2
    assert notes["verdict"] == \
        f"Take 2 of 2 is best (take 1: Character 7's face 0.21); {held}; re-takes used 1.6 of 15 min"
    assert notes["verdicts"]["clips/b.mp4"] == f"Take 2 of 2 · best · {held}"
    assert notes["verdicts"]["clips/a.mp4"].startswith("Take 1 of 2 · Character 7's face scored 0.21 (0.30 is the bar)")


def test_finish_says_one_line_when_take_1_passed_and_under_the_bar_after_its_takes(ctx):  # noqa: F811
    plan = presstakes.plan(ctx, continue_plan())
    plan.judge.shots[0] = {"lines": [{"speaker": "Character 7", "words": LINE}], "camera": {}}
    one = notes_of(plan, {1: reading(FACE)}, {1: "clips/a.mp4"})
    assert one == {"verdict": "Character 7's face held (0.44); Character 7's mouth moves with the words (0.71); "
                              "heard 100% of the words", "best": "clips/a.mp4", "best_task": 1}, \
        "no Take prefix, no chips"
    plan = presstakes.plan(ctx, continue_plan())
    plan.judge.shots[0] = copy.deepcopy({"lines": [{"speaker": "Character 7", "words": LINE}], "camera": {}})
    under = notes_of(plan, {1: reading(POOR), 2: reading(POOR, heard=0.5)}, {1: "clips/a.mp4", 2: "clips/b.mp4"})
    assert under["best"] == "clips/a.mp4"
    assert under["verdict"].startswith("Best of 2 takes, under the bar: Character 7's face")
    assert under["verdicts"]["clips/a.mp4"].startswith("Take 1 of 2 · best · ")
    assert plan.finish.notes({}, plan.judge.seen) == {}, "no take landed: nothing noted"


def test_a_lines_takes_are_judged_on_the_words(ctx):  # noqa: F811
    plan = presstakes.plan(ctx, line_plan())
    bad, good = {"words": {"heard": 0.6, "first_miss": 1.2}}, {"words": {"heard": 0.95, "first_miss": None}}
    notes = notes_of(plan, {1: bad, 2: good}, {1: "sounds/a.wav", 2: "sounds/b.wav"})
    assert notes["best"] == "sounds/b.wav"
    assert notes["verdict"] == "Take 2 of 2 is best (take 1: heard 60%); Heard 95% of the words; re-takes used 1.6 " \
                               "of 15 min"
    assert notes["verdicts"]["sounds/a.wav"] == "Take 1 of 2 · Heard 60% of the words; the first miss at 1.2 s"


async def test_generates_seed_is_sent_as_today(ctx, monkeypatch):  # noqa: F811
    """Generate's "random" and a fixed seed are sent whole, takes on seed + 1, `last_seeds` kept."""
    pick(ctx, REF2VA, CHARACTER_7)
    monkeypatch.setattr(build.prerun, "engine_plan", _none)
    for value in ("random", "41"):
        await call(ctx, "set_generate_image_settings", {"seed": value})
        job = await press(ctx, character_7_alone())
        sent = [t["seed"] for t in presstakes.plan(ctx, job.plan).tasks]
        assert all(isinstance(s, int) for s in sent) and sent == [sent[0], sent[0] + 1]
        assert job.plan.summary["seeds"] == [sent[0]] and (value == "random" or sent[0] == 41)
        ctx.jobs.jobs[job.id] = (job, {})
        await build.on_submitted(ctx, {"job": job.id, "kind": f"{ctx.module_id}.image", "by": ctx.module_id})
        assert routes.session_part(ctx)["last_seeds"] == {"model": REF2VA, "seeds": [sent[0]]}
        ctx.jobs.jobs.clear()


async def _none(*_: Any) -> None:
    return None
