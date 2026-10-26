"""A plan's takes, pure. `check` refuses takes that are not disjoint runs of steps in order, takes of
one shot of unequal length, and a "best" source that is not the last step of a shot's first take, each in one line;
`runs` says which take's step is sent (take 1 always; take t after a take under the bar or failed, when the judge
allows it; a take's later step when its first made a file); `best` picks the cut's take; `fill` resolves "best"."""
from __future__ import annotations

from typing import Any

import pytest

from hub.core import jobgraph
from hub.core.api import Invalid, JobPlan, Take
from hub.worker import engineapi, enginewire

PASS, FAIL = Take(True, (1.0, 3.0, 1.4), "held"), Take(False, (0.0, 2.0, 0.7), "under")
FAILED = Take(False, (), "take 1 failed: Out of memory")


def clip(seed: int = 1) -> dict:
    return enginewire.request_wire(engineapi.ClipRequest("h3", "a shot", (960, 544), seed, 124))


def voice() -> dict:
    return enginewire.request_wire(engineapi.VoiceRequest("", "/chars/Character 7.wav", 7))


def cut(n: int = 2) -> dict:
    item = engineapi.JoinItem("", 0, 124, 24.0, 960, 544, 124, True)
    return enginewire.request_wire(engineapi.JoinRequest([item] * n, engineapi.Canvas(960, 544, 24.0), [], 18,
                                                         "medium"))


def plan(takes: Any, best: tuple[int, int] = (1, 3), tasks: int = 4) -> JobPlan:
    """`tasks` clips, then the cut reading `best` as each shot's best."""
    inputs = (*({} for _ in range(tasks)), {"items.0.path": (best[0], "best"), "items.1.path": (best[1], "best")})
    return JobPlan("image", "h3", (*(clip(k) for k in range(1, tasks + 1)), cut()), {}, inputs=inputs, takes=takes)


class Judge:
    def __init__(self, allow: bool = True) -> None:
        self.allow = allow

    def done(self, task: int, d: Any) -> Take | None:
        return None

    def again(self, shot: int, take: int) -> bool:
        return self.allow


@pytest.mark.parametrize("takes, line", [
    ((((1,), (2,)), ((2,), (3,))), "Shot 2's takes are not runs of steps in order"),          # overlapping
    ((((3,), (4,)), ((1,), (2,))), "Shot 2's takes are not runs of steps in order"),          # out of order
    ((((1, 3), (4, 5)),), "Shot 1's takes are not runs of steps in order"),                  # not a run
    ((((1,), (2, 3)),), "Shot 1's takes are not of equal length"),                           # unequal
])
def test_check_refuses_takes_that_are_not_ordered_runs(takes, line):
    with pytest.raises(Invalid) as err:
        jobgraph.check(plan(takes, best=(1, 1)))
    assert err.value.text == line


def test_check_refuses_a_best_source_that_ends_no_first_take():
    with pytest.raises(Invalid) as err:
        jobgraph.check(plan((((1,), (2,)), ((3,), (4,))), best=(2, 3)))
    assert err.value.text == "Step 5's items.0.path reads step 2, which ends no shot's first take"
    jobgraph.check(plan((((1,), (2,)), ((3,), (4,)))))                      # take 1's last steps: accepted


def test_runs_take_1_always_and_take_2_only_after_a_take_under_the_bar():
    p, j = plan((((1,), (2,)), ((3,), (4,)))), Judge()
    assert jobgraph.runs(p, 1, {}, {}, j) and jobgraph.runs(p, 3, {}, {}, j) and jobgraph.runs(p, 5, {}, {}, j)
    assert not jobgraph.runs(p, 2, {1: PASS}, {1: "a"}, j), "a take that passed: skipped"
    assert jobgraph.runs(p, 2, {1: FAIL}, {1: "a"}, j), "under the bar: rendered again"
    assert jobgraph.runs(p, 2, {1: FAILED}, {}, j), "a failed take: rendered again"
    assert not jobgraph.runs(p, 2, {1: FAIL}, {1: "a"}, Judge(allow=False)), "the judge refuses: skipped"
    assert not jobgraph.runs(p, 2, {}, {}, j), "take 1 never ran: skipped"
    assert not jobgraph.runs(p, 2, {1: FAIL}, {1: "a"}, None)


def test_a_takes_voice_step_runs_only_after_its_render_made_a_file():
    p = JobPlan("image", "h3", (clip(), voice(), clip(), voice(), cut(1)), {},
                inputs=({}, {"clip": (1, "file")}, {}, {"clip": (3, "file")}, {"items.0.path": (2, "best")}),
                takes=(((1, 2), (3, 4)),))
    jobgraph.check(p)
    j = Judge()
    assert jobgraph.runs(p, 2, {1: PASS}, {1: "/r.mp4"}, j)
    assert not jobgraph.runs(p, 4, {1: FAIL}, {}, j), "its render skipped: nothing to convert"
    assert not jobgraph.runs(p, 4, {1: FAIL, 3: FAILED}, {}, j), "its render failed"


def test_best_picks_the_passing_take_else_the_highest_rank_ties_the_earlier_a_failed_take_last():
    p = plan((((1,), (2,)), ((3,), (4,))))
    made = {1: "a", 2: "b", 3: "c", 4: "d"}
    assert jobgraph.best(p, 1, {1: FAIL, 2: PASS}, made) == 2
    assert jobgraph.best(p, 1, {1: FAIL, 2: Take(False, (0.0, 2.0, 0.9), "x")}, made) == 2
    assert jobgraph.best(p, 1, {1: PASS, 2: PASS}, made) == 1, "ties: the earlier"
    assert jobgraph.best(p, 2, {3: FAIL, 4: FAILED}, {3: "c"}) == 3, "a failed take made nothing"
    assert jobgraph.best(p, 2, {}, {}) is None


def test_fill_resolves_best_to_the_shots_best_take():
    p = plan((((1,), (2,)), ((3,), (4,))))
    made = {1: "/one.mp4", 2: "/two.mp4", 3: "/three.mp4"}
    sent = jobgraph.fill(p.tasks[4], p.inputs[4], made, 5, p, {1: FAIL, 2: PASS, 3: PASS})
    assert [i["path"] for i in sent["items"]] == ["/two.mp4", "/three.mp4"]


def test_absorbs_a_failure_while_a_take_is_made_or_one_is_left():
    p = plan((((1,), (2,)), ((3,), (4,))))
    assert jobgraph.absorbs(p, 1, {}, Judge()), "take 2 is left"
    assert not jobgraph.absorbs(p, 1, {}, Judge(allow=False))
    assert jobgraph.absorbs(p, 2, {1: "a"}, Judge()), "take 1 was made"
    assert not jobgraph.absorbs(p, 2, {}, Judge()) and not jobgraph.absorbs(p, 5, {}, Judge())
