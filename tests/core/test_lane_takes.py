"""A scene's takes on the real engine lane and dispatcher, the fake worker of the lane tests behind
them. Two shots × two takes: take 2 of a shot runs only when the plan's judge found take 1 under the bar and allows
it, else it is skipped (`skip`); the cut reads each shot's best take ("best"). A re-take's failed render is a bad
take, not a failed job; a crash still ends the job. A plan without `takes` runs as in the lane tests."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from hub.core import api
from hub.worker import engineapi, enginewire
from tests.core.test_engine_graph import MODEL, Sup, clip, run

ITEM = engineapi.JoinItem("", 0, 124, 24.0, 960, 544, 124, True)


class Judge:
    """A judge step that fails the takes it is told to and allows every re-take (unless `allow` is False)."""

    def __init__(self, failing: set[int], allow: bool = True) -> None:
        self.failing, self.allow, self.asked = failing, allow, []

    def done(self, task: int, d: Mapping[str, Any]) -> api.Take | None:
        ok = task not in self.failing
        return api.Take(ok, (1.0 if ok else 0.0, 0.0, 0.5), "held" if ok else "under the bar")

    def again(self, shot: int, take: int) -> bool:
        self.asked.append((shot, take))
        return self.allow


def scene(judge: Any) -> api.JobPlan:
    """Shot 1 = tasks 1-2 (takes), shot 2 = tasks 3-4, then the cut reading each shot's best take."""
    cut = enginewire.request_wire(engineapi.JoinRequest([ITEM, ITEM], engineapi.Canvas(960, 544, 24.0), [], 18,
                                                        "medium"))
    return api.JobPlan("image", MODEL, (clip(1), clip(2), clip(3), clip(4), cut),
                       {"model": "H3", "kind": "clip", "mode": "scene"},
                       inputs=({}, {}, {}, {}, {"items.0.path": (1, "best"), "items.1.path": (3, "best")}),
                       takes=(((1,), (2,)), ((3,), (4,))), judge=judge)


def path_of(tmp_path: Path, item: str) -> str:
    return str(tmp_path / "data" / "clips" / item.split("/", 1)[1])


async def test_a_take_that_passes_is_not_rendered_again_and_one_under_the_bar_is(tmp_path, monkeypatch):
    judge = Judge({3})
    job, lane, emitted, _, _, _ = await run(tmp_path, monkeypatch, scene(judge))
    assert job.state == "done", job.error
    assert [d["task"] for e, d in emitted if e == "task"] == [1, 3, 4, 5]
    assert [d for e, d in emitted if e == "skip"] == [{"task": 2, "of": 5}]
    assert [r["seed"] for r in lane.sup.sent[:3]] == [1, 3, 4] and judge.asked == [(2, 2)]
    out = {d["task"]: d["item"] for e, d in emitted if e == "output"}
    items = lane.sup.sent[3]["items"]
    assert [i["path"] for i in items] == [path_of(tmp_path, out[1]), path_of(tmp_path, out[4])]
    assert job.notes["takes"] == {"1": {"passes": True, "line": "held"}, "3": {"passes": False,
                                                                           "line": "under the bar"},
                                  "4": {"passes": True, "line": "held"}}


async def test_a_retake_the_judge_refuses_is_skipped_and_the_cut_takes_take_1(tmp_path, monkeypatch):
    job, lane, emitted, _, _, _ = await run(tmp_path, monkeypatch, scene(Judge({1, 3}, allow=False)))
    assert job.state == "done", job.error
    assert [d["task"] for e, d in emitted if e == "skip"] == [2, 4]
    out = {d["task"]: d["item"] for e, d in emitted if e == "output"}
    assert [i["path"] for i in lane.sup.sent[2]["items"]] == [path_of(tmp_path, out[1]), path_of(tmp_path, out[3])]


async def test_a_retakes_failed_render_is_a_bad_take_and_the_job_is_done(tmp_path, monkeypatch):
    job, lane, emitted, _, _, _ = await run(tmp_path, monkeypatch, scene(Judge({3})), fail={4: "Out of memory"})
    assert job.state == "done" and job.error is None
    assert job.takes[4] == api.Take(False, (), "take 2 failed: Out of memory")
    assert job.notes["takes"]["4"] == {"passes": False, "line": "take 2 failed: Out of memory"}
    out = {d["task"]: d["item"] for e, d in emitted if e == "output"}
    assert [i["path"] for i in lane.sup.sent[-1]["items"]] == [path_of(tmp_path, out[1]), path_of(tmp_path, out[3])]


async def test_a_first_take_that_fails_with_a_retake_left_renders_it(tmp_path, monkeypatch):
    job, lane, emitted, _, _, _ = await run(tmp_path, monkeypatch, scene(Judge(set())), fail={1: "Out of memory"})
    assert job.state == "done", job.error
    assert [d["task"] for e, d in emitted if e == "task"] == [1, 2, 3, 5]
    out = {d["task"]: d["item"] for e, d in emitted if e == "output"}
    assert [i["path"] for i in lane.sup.sent[-1]["items"]] == [path_of(tmp_path, out[2]), path_of(tmp_path, out[3])]


async def test_a_shot_with_no_take_made_and_none_left_stops_the_scene(tmp_path, monkeypatch):
    job, _, _, _, _, _ = await run(tmp_path, monkeypatch, scene(Judge(set())), fail={1: "Bad", 2: "Worse"})
    assert job.state == "failed" and job.error == "Worse"


class Crash(Sup):
    """The worker dies on the tasks in `crash`."""

    crash: set[int] = set()

    async def send(self, msg: dict) -> None:
        if msg.get("op") == "run" and int(msg["task"]) in self.crash:
            self.sent.append(msg["request"])
            import asyncio
            asyncio.get_running_loop().call_soon(self.on_event, {"ev": "exit", "crash": True, "text": "Killed"})
            return
        await super().send(msg)


async def test_a_crash_in_a_retake_is_not_absorbed(tmp_path, monkeypatch):
    monkeypatch.setattr(Crash, "crash", {4})
    import tests.core.test_engine_graph as graph
    monkeypatch.setattr(graph, "Sup", Crash)
    job, _, _, _, _, _ = await run(tmp_path, monkeypatch, scene(Judge({3})))
    assert job.state == "failed" and job.error == "Killed"


async def test_a_plan_without_takes_asks_no_judge(tmp_path, monkeypatch):
    judge = Judge({1})
    plan = api.JobPlan("image", MODEL, (clip(1), clip(2)), {"model": "H3", "kind": "clip"}, judge=judge)
    job, _, emitted, _, _, _ = await run(tmp_path, monkeypatch, plan)
    assert job.state == "done" and "takes" not in job.notes and job.takes == {} and judge.asked == []
    assert not [e for e, _ in emitted if e == "skip"]


class PressJudge(Judge):
    """A press's judge as `presstakes.Finish` reads it: its verdicts kept (`seen`), its short words."""

    def __init__(self, failing: set[int], allow: bool = True) -> None:
        super().__init__(failing, allow)
        self.seen: dict[int, api.Take] = {}
        self.short: dict[int, str] = {}
        self.cap = 900.0

    def done(self, task: int, d: Mapping[str, Any]) -> api.Take | None:
        self.seen[task] = take = super().done(task, d)
        return take

    def used(self) -> float:
        return 0.0


def one_shot(judge: Any, noted: dict) -> api.JobPlan:
    """A press of two takes (`presstakes.plan`'s shape), its last step the press's own `Finish`."""
    from types import SimpleNamespace

    from hub.modules.generate_image import presstakes

    jobs = SimpleNamespace(get=lambda _id: SimpleNamespace(id="j", takes={}), note=lambda _id, **v: noted.update(v))
    finish = presstakes.Finish(SimpleNamespace(jobs=jobs), judge, (((1,), (2,)),), job="j")
    return api.JobPlan("image", MODEL, (clip(1), clip(2)), {"model": "H3", "kind": "clip"},
                       takes=(((1,), (2,)),), judge=judge, finish=finish)


async def test_a_press_whose_take_1_fails_runs_both_and_marks_take_2_best(tmp_path, monkeypatch):
    noted: dict = {}
    job, _, emitted, _, _, _ = await run(tmp_path, monkeypatch, one_shot(PressJudge({1}), noted))
    assert job.state == "done", job.error
    assert [d["task"] for e, d in emitted if e == "task"] == [1, 2]
    out = {d["task"]: d["item"] for e, d in emitted if e == "output"}
    assert noted["best"] == out[2] and noted["verdicts"][out[2]].startswith("Take 2 of 2 · best")


async def test_a_press_whose_take_1_passes_skips_take_2(tmp_path, monkeypatch):
    noted: dict = {}
    job, _, emitted, _, _, _ = await run(tmp_path, monkeypatch, one_shot(PressJudge(set()), noted))
    assert job.state == "done" and [d for e, d in emitted if e == "skip"] == [{"task": 2, "of": 2}]
    out = {d["task"]: d["item"] for e, d in emitted if e == "output"}
    assert noted == {"verdict": "held", "best": out[1], "best_task": 1}


async def test_a_press_take_2s_failed_render_is_absorbed(tmp_path, monkeypatch):
    noted: dict = {}
    job, _, _, _, _, _ = await run(tmp_path, monkeypatch, one_shot(PressJudge({1}), noted), fail={2: "Out of memory"})
    assert job.state == "done" and job.error is None and job.takes[2].line == "take 2 failed: Out of memory"
    assert noted["verdict"].startswith("Best of 2 takes, under the bar: under the bar")
