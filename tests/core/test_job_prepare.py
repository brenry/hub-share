"""A job that plans itself. A plan with `prepare` is queued with no tasks; when it starts, `prepare`
runs before `lane.run` and its `say` lines reach the card as phase `planning`; its plan replaces the job's; a raise
fails the job with that line; a cancel while it runs cancels the job and the lane never runs; a returned plan for
another model or with no tasks fails in one line; a plan without `prepare` gives the recorded cards, event for event."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from hub.core.api import Ctx, Invalid, JobPlan, Module, Tab
from tests.core.fake_lane import FakeLane
from tests.core.harness import Hub, own_modules, start_hub
from tests.fakes.fake_probes import FakeProbes

STEP: dict[str, Any] = {}          # what the test's `prepare` does: its lines, its gate, its answer


async def prepare(say) -> JobPlan:  # type: ignore[no-untyped-def]
    STEP["ran"] = True
    for line in STEP.get("lines", ()):
        say(line)
    if STEP.get("gate") is not None:
        await STEP["gate"].wait()
    if STEP.get("raise"):
        raise Invalid("shot", STEP["raise"])
    return STEP.get("plan", JobPlan("image", "flux", ({"seed": 7},), {"model": "Flux", "prompt": "the render"}))


def build(params: dict, ctx: Ctx) -> JobPlan:
    summary = {"model": "Flux", "prompt": params["prompt"]}
    if params.get("plans"):
        return JobPlan("image", "flux", (), {**summary, "kind": "clip"}, prepare=prepare)
    return JobPlan("image", "flux", ({"seed": 100},), summary)


GEN = Module(id="gen", title="Gen", tab=Tab("Gen", 10), jobs={"image": build})


@pytest.fixture
async def hub(tmp_path: Path):  # type: ignore[no-untyped-def]
    STEP.clear()
    probes = FakeProbes()
    lane = FakeLane(tmp_path / "data" / "outputs", probes)
    h = await start_hub(tmp_path / "data", lanes=[lane], modules=[*own_modules(), GEN], probes=probes)
    h.lane = lane  # type: ignore[attr-defined]
    yield h
    await h.close()


async def cards(hub: Hub, params: dict, until: str = "done") -> tuple[str, list[dict]]:
    """Submit and collect the job's cards until it is `until`."""
    w = await hub.screen(hub.pair(), "workspace", "w")
    job = hub.core.book.submit("gen.image", params)
    seen: list[dict] = []
    while True:
        m = await w.recv("job", where=lambda x: x["d"]["id"] == job.id, timeout=5)
        seen.append(m["d"])
        if m["d"]["state"] == until:
            return job.id, seen


async def test_a_plan_with_prepare_is_queued_with_no_tasks_and_plans_before_the_lane_runs(hub: Hub) -> None:
    STEP["lines"] = ["Planning · ask 1 · qwen", "Planning · fixing: action 1 holds a quote · ask 2 · qwen"]
    STEP["gate"] = asyncio.Event()
    asyncio.get_running_loop().call_later(0.3, STEP["gate"].set)     # the model writes for a while
    job_id, seen = await cards(hub, {"prompt": "Prompt 1.", "plans": True})
    assert seen[0]["state"] == "queued" and seen[0]["summary"]["prompt"] == "Prompt 1."
    planning = [c["progress"]["text"] for c in seen if (c["progress"] or {}).get("phase") == "planning"]
    assert planning == STEP["lines"], "each say line reaches the card"
    after = [c for c in seen if c["summary"]["prompt"] == "the render"]
    assert after and all((c["progress"] or {}).get("phase") != "planning" for c in after)
    assert seen[-1]["state"] == "done" and seen[-1]["summary"]["prompt"] == "the render", "the render's summary"
    assert hub.lane.runs == [job_id]  # type: ignore[attr-defined]
    assert hub.core.book.entries[job_id].job.plan.tasks == ({"seed": 7},), "its plan replaced the job's"


async def test_a_raise_in_prepare_fails_the_job_in_its_line_and_nothing_runs(hub: Hub) -> None:
    STEP["raise"] = "Planning: refused 3 times; last: action 1 holds a quote; spoken words go in lines only"
    job_id, seen = await cards(hub, {"prompt": "x", "plans": True}, until="failed")
    assert seen[-1]["error"] == {"text": STEP["raise"]}
    assert hub.lane.runs == []  # type: ignore[attr-defined]


async def test_a_cancel_while_it_plans_cancels_the_job_and_never_runs_the_lane(hub: Hub) -> None:
    STEP["gate"] = asyncio.Event()
    STEP["lines"] = ["Planning · ask 1 · qwen"]
    w = await hub.screen(hub.pair(), "workspace", "w")
    job = hub.core.book.submit("gen.image", {"prompt": "x", "plans": True})
    await w.recv("job", where=lambda x: (x["d"]["progress"] or {}).get("phase") == "planning", timeout=5)
    hub.core.book.cancel(job.id)
    end = await w.recv("job", where=lambda x: x["d"]["state"] == "cancelled", timeout=5)
    assert end["d"]["id"] == job.id and end["d"]["error"] is None
    assert hub.lane.runs == [] and not hub.lane.cancelled  # type: ignore[attr-defined]


@pytest.mark.parametrize("plan, line", [
    (JobPlan("image", "wan", ({"seed": 1},), {"model": "Wan"}), "Planning gave a job for another model"),
    (JobPlan("image", "flux", (), {"model": "Flux"}), "Planning gave nothing to run"),
    (JobPlan("image", "flux", ({"seed": 1},), {}, prepare=prepare), "Planning gave nothing to run"),
])
async def test_a_returned_plan_for_another_model_or_with_no_tasks_fails_in_one_line(hub: Hub, plan: JobPlan,
                                                                                   line: str) -> None:
    STEP["plan"] = plan
    _, seen = await cards(hub, {"prompt": "x", "plans": True}, until="failed")
    assert seen[-1]["error"] == {"text": line}
    assert hub.lane.runs == []  # type: ignore[attr-defined]


# The cards of a one-image job without `prepare`, recorded on the dispatcher with this
# test's module and lane; the clock times, the job's id and the estimate left out.
CARD = {"cancel_requested": False, "error": None, "kind": "gen.image", "lane": "image.gpu0", "notes": {},
        "outputs": [], "position": None, "progress": None, "state": "running", "title": "1 image · Flux",
        "summary": {"model": "Flux", "prompt": "a cat"}, "tool": "gen"}
RUN = {"count": 1, "eta_s": None, "index": 1, "pct": 0, "phase": None, "step": 0, "steps": 0, "text": None}
BEFORE = [{**CARD, "state": "queued", "position": 1},
          {**CARD, "progress": {**RUN, "index": 0}},
          {**CARD, "progress": {**RUN, "phase": "loading", "text": "Loading Flux"}},
          {**CARD, "outputs": ["out/2026-10-09/J_1.png"],
           "progress": {**RUN, "pct": 100, "phase": "inference", "step": 4, "steps": 4, "text": "Denoising"}},
          {**CARD, "state": "done", "outputs": ["out/2026-10-09/J_1.png"]}]


def _plain(card: dict, job_id: str) -> dict:
    out = {k: v for k, v in card.items() if k not in ("created", "started", "id")}
    out["outputs"] = [o.replace(job_id, "J") for o in out["outputs"]]
    if out["progress"]:
        out["progress"] = {**out["progress"], "eta_s": None}
    return out


async def test_a_plan_without_prepare_goes_as_it_did(hub: Hub) -> None:
    job_id, seen = await cards(hub, {"prompt": "a cat"})
    assert [_plain(c, job_id) for c in seen] == BEFORE
    assert hub.lane.runs == [job_id]  # type: ignore[attr-defined]
