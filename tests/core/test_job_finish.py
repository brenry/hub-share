"""A job's last step. A plan with `finish` has it awaited after the lane's run whatever its end (done,
failed, cancelled), given the media id each task landed (task -> id); a raise in it fails a done job with
`Sequence: <line>` and leaves a failed one's line; a plan without it gives a plain job's cards, card for card."""
from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from hub.core.api import Ctx, JobPlan, Module, Tab
from tests.core.fake_lane import FakeLane
from tests.core.harness import Hub, own_modules, start_hub
from tests.core.test_job_prepare import BEFORE, _plain
from tests.fakes.fake_probes import FakeProbes

SEEN: dict[str, Any] = {}


async def finish(landed: Mapping[int, str]) -> None:
    SEEN.setdefault("calls", []).append(dict(landed))
    if SEEN.get("raise"):
        raise ValueError(SEEN["raise"])


def build(params: dict, ctx: Ctx) -> JobPlan:
    summary = {"model": "Flux", "prompt": params["prompt"]}
    if params.get("finish"):
        return JobPlan("image", "flux", ({"seed": 1}, {"seed": 2}, {"seed": 3}), summary, finish=finish)
    return JobPlan("image", "flux", ({"seed": 100},), summary)


GEN = Module(id="gen", title="Gen", tab=Tab("Gen", 10), jobs={"image": build})


@pytest.fixture
async def hub(tmp_path: Path):  # type: ignore[no-untyped-def]
    SEEN.clear()
    probes = FakeProbes()
    lane = FakeLane(tmp_path / "data" / "outputs", probes)
    h = await start_hub(tmp_path / "data", lanes=[lane], modules=[*own_modules(), GEN], probes=probes)
    h.lane = lane  # type: ignore[attr-defined]
    yield h
    await h.close()


async def cards(hub: Hub, params: dict, until: str, cancel_at: int | None = None) -> tuple[str, list[dict]]:
    w = await hub.screen(hub.pair(), "workspace", "w")
    job = hub.core.book.submit("gen.image", params)
    seen: list[dict] = []
    while True:
        m = await w.recv("job", where=lambda x: x["d"]["id"] == job.id, timeout=5)
        seen.append(m["d"])
        if cancel_at is not None and len(m["d"]["outputs"]) == cancel_at and m["d"]["state"] == "running":
            hub.core.book.cancel(job.id)
            hub.lane.gate.set()  # type: ignore[attr-defined]
            cancel_at = None
        if m["d"]["state"] == until:
            return job.id, seen


def ids(job_id: str, *tasks: int) -> dict[int, str]:
    return {k: f"out/2026-10-09/{job_id}_{k}.png" for k in tasks}


async def test_finish_runs_after_a_done_run_with_the_landed_ids_by_task(hub: Hub) -> None:
    job_id, seen = await cards(hub, {"prompt": "x", "finish": True}, "done")
    assert SEEN["calls"] == [ids(job_id, 1, 2, 3)] and seen[-1]["error"] is None


async def test_finish_runs_after_a_failed_run_with_what_was_made(hub: Hub) -> None:
    hub.lane.fail_at = 3  # type: ignore[attr-defined]
    job_id, seen = await cards(hub, {"prompt": "x", "finish": True}, "failed")
    assert SEEN["calls"] == [ids(job_id, 1, 2)]
    assert seen[-1]["error"] == {"text": "Out of GPU memory"}, "a failed job keeps its line"


async def test_finish_runs_after_a_cancel_with_what_was_made(hub: Hub) -> None:
    hub.lane.gate = asyncio.Event()  # type: ignore[attr-defined]
    asyncio.get_running_loop().call_later(0.05, hub.lane.gate.set)  # type: ignore[attr-defined]
    hub.lane.steps = 1  # type: ignore[attr-defined]
    real = hub.lane.run  # type: ignore[attr-defined]

    async def gated(job: Any, emit: Any) -> None:                      # the gate shuts after task 1's file
        def held(ev: str, d: dict) -> None:
            emit(ev, d)
            if ev == "output" and d.get("task") == 1:
                hub.lane.gate = asyncio.Event()  # type: ignore[attr-defined]
        await real(job, held)
    hub.lane.run = gated  # type: ignore[attr-defined]
    job_id, _ = await cards(hub, {"prompt": "x", "finish": True}, "cancelled", cancel_at=1)
    assert SEEN["calls"] == [ids(job_id, 1)]


async def test_a_raise_in_finish_fails_a_done_job_with_its_line(hub: Hub) -> None:
    SEEN["raise"] = "There is no sequence named x\nmore"
    _, seen = await cards(hub, {"prompt": "x", "finish": True}, "failed")
    assert seen[-1]["error"] == {"text": "Sequence: There is no sequence named x"}
    assert len(seen[-1]["outputs"]) == 3, "the files stay the job's"


async def test_a_raise_in_finish_leaves_a_failed_jobs_line(hub: Hub) -> None:
    SEEN["raise"] = "anything"
    hub.lane.fail_at = 2  # type: ignore[attr-defined]
    _, seen = await cards(hub, {"prompt": "x", "finish": True}, "failed")
    assert seen[-1]["error"] == {"text": "Out of GPU memory"}


async def test_a_plan_without_finish_goes_as_it_did(hub: Hub) -> None:
    job_id, seen = await cards(hub, {"prompt": "a cat"}, "done")
    assert [_plain(c, job_id) for c in seen] == BEFORE and "calls" not in SEEN
