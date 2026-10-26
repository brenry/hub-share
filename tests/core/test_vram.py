"""The VRAM manager with FakeProbes: reads only at decision points, never waits on other programs, idle unload,
the snapshot."""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from hub.core.api import Ctx, JobPlan, Module, Tab
from tests.core.fake_lane import FakeLane
from tests.core.harness import Hub, own_modules, start_hub
from tests.fakes.fake_probes import GB, FakeProbes


def build(params: dict, ctx: Ctx) -> JobPlan:
    return JobPlan("image", params.get("model", "flux"), ({"seed": 1},), {"model": "Flux"})


GEN = Module(id="gen", title="Gen", tab=Tab("Gen", 10), jobs={"image": build})


async def make(tmp_path: Path, **settings: dict) -> tuple[Hub, FakeLane, FakeProbes]:
    probes = FakeProbes()
    lane = FakeLane(tmp_path / "data" / "outputs", probes, steps=2)
    hub = await start_hub(tmp_path / "data", lanes=[lane], modules=[*own_modules(), GEN], probes=probes,
                          settings=settings or None)
    hub.core.vram.share_s = 0.0  # every decision point reads (normally two within 1 s share one)
    return hub, lane, probes


async def run_job(hub: Hub, w: object, rid: str = "r") -> str:
    await w.send("job.submit", {"tool": "gen", "kind": "image", "params": {}}, id=rid)  # type: ignore[attr-defined]
    job = (await w.recv("reply", where=lambda x: x["re"] == rid))["d"]["job"]  # type: ignore[attr-defined]
    await w.recv("job", where=lambda x: x["d"]["id"] == job and x["d"]["state"] in ("done", "failed"),  # type: ignore
                 timeout=5)
    return job


async def test_reads_happen_only_at_decision_points_and_an_idle_hub_reads_nothing(tmp_path: Path) -> None:
    hub, lane, probes = await make(tmp_path, vram={"idle_unload": False})
    try:
        hub.core.vram.settle_s = 0.05
        assert probes.reads == 1      # boot
        w = await hub.screen(hub.pair(), "workspace", "w")
        assert probes.reads == 1      # a new screen reuses a reading under 5 s old
        for i in range(5):
            await run_job(hub, w, f"r{i}")
        await asyncio.sleep(0.2)
        # per job: the dispatch plan + the job's end; once: the model-loaded event and the reading after it settles
        assert probes.reads == 1 + 5 * 2 + 1 + 1
        settled = probes.reads
        await asyncio.sleep(1.5)
        assert probes.reads == settled  # idle: no timer reads anything
        t0 = time.time()
        for _ in range(3):
            await w.send("gpu.refresh")
        await w.recv("gpu", where=lambda x: x["d"]["read_at"] >= t0)
        await asyncio.sleep(0.2)
        assert probes.reads == settled + 1  # refreshes within 1 s share one reading
    finally:
        await hub.close()


async def test_other_programs_memory_never_holds_a_job(tmp_path: Path) -> None:
    hub, lane, probes = await make(tmp_path)
    try:
        hub.core.vram.learn("vram", "flux", "GPU-fake-0", 20 * GB)
        probes.set_procs({999: 31 * GB})                      # another program fills the card
        w = await hub.screen(hub.pair(), "workspace", "w")
        await w.send("job.submit", {"tool": "gen", "kind": "image", "params": {}}, id="r")
        records = [(await w.recv("job"))["d"]]
        while records[-1]["state"] != "done":
            records.append((await w.recv("job", timeout=5))["d"])
        assert all("hold" not in r and "note" not in r for r in records)
        assert [x["state"] for x in hub.core.vram.snapshot()["gpus"][0]["lanes"]] == ["ready"]
    finally:
        await hub.close()


async def test_a_different_model_is_released_before_the_job_runs(tmp_path: Path) -> None:
    hub, lane, probes = await make(tmp_path, vram={"idle_unload": False})
    try:
        lane.model = "qwen"
        lane._usage(12_000)
        w = await hub.screen(hub.pair(), "workspace", "w")
        await run_job(hub, w)
        assert lane.released == ["for Flux"] and lane.model == "flux"
    finally:
        await hub.close()


async def test_idle_unload_arms_cancels_and_fires(tmp_path: Path) -> None:
    hub, lane, probes = await make(tmp_path, vram={"idle_minutes": 5})
    try:
        vram = hub.core.vram
        vram.minute_s = 0.04
        w = await hub.screen(hub.pair(), "workspace", "w")
        await run_job(hub, w)
        await asyncio.sleep(0.05)
        assert "image.gpu0" in vram._idle
        await run_job(hub, w, "r2")
        assert lane.released == []
        await asyncio.sleep(0.35)
        assert lane.released == ["idle"] and lane.model is None and "image.gpu0" not in vram._idle
        snap = vram.snapshot()["gpus"][0]
        assert snap["lanes"][0] == {"id": "image.gpu0", "kind": "image", "state": "idle", "model": None}
    finally:
        await hub.close()


async def test_snapshot_names_each_gpu_and_says_when_it_cannot_read_one(tmp_path: Path) -> None:
    hub, lane, probes = await make(tmp_path)
    try:
        assert hub.core.vram.snapshot()["gpus"] == [
            {"uuid": "GPU-fake-0", "name": "Fake RTX", "total_mb": 32 * GB, "used_mb": 0, "free_mb": 32 * GB,
             "lanes": [{"id": "image.gpu0", "kind": "image", "state": "idle", "model": None}],
             "unknown": False}]
        probes.gpu_list = None
        hub.core.vram.read(max_age=0)
        assert hub.core.vram.snapshot()["gpus"][0]["unknown"] is True
        plan = hub.core.vram.plan(lane, "flux", "Flux")
        assert (plan.light, plan.action) == ("amber", "run")
    finally:
        await hub.close()


def test_the_lane_change_hook_is_wired(tmp_path: Path) -> None:
    pytest.importorskip("hub.core.vram")
    from hub.core.vram import Vram
    lane = FakeLane(tmp_path, FakeProbes())
    calls: list[str] = []

    class Bus:
        def publish(self, *a: object, **k: object) -> None:
            calls.append("published")

    v = Vram(FakeProbes(), lambda: {"vram": {}}, Bus())
    v.register_lane(lane)
    lane.on_change()
    assert calls.count("published") == 2


async def test_the_learned_peak_leaves_out_other_programs(tmp_path: Path) -> None:
    hub, lane, probes = await make(tmp_path, vram={"idle_unload": False})
    try:
        probes.set_procs({999: 5_000})                         # another program's memory: the baseline
        w = await hub.screen(hub.pair(), "workspace", "w")
        await run_job(hub, w)
        assert hub.core.vram.need("vram", "flux", "GPU-fake-0") == 14_000 - 5_000  # the card's peak less the baseline
    finally:
        await hub.close()


async def test_media_clears_the_cache_and_queues_a_generation(tmp_path: Path) -> None:
    hub, lane, probes = await make(tmp_path)
    try:
        c = hub.pair()
        m = await hub.screen(c, "media", "m")
        await m.send("gpu.release", {}, id="r1")
        ok = await m.recv("reply", where=lambda x: x.get("re") == "r1")
        assert "ok" in ok["d"]
        await m.send("gpu.release", {"lane": "nope"}, id="r2")
        refused = await m.recv("error", where=lambda x: x.get("re") == "r2")
        assert refused["d"]["text"] == "That GPU is busy"
        await m.send("job.submit", {"tool": "gen", "kind": "image", "params": {}}, id="r3")
        queued = await m.recv("reply", where=lambda x: x.get("re") == "r3")
        assert queued["d"]["state"] in ("queued", "running")
    finally:
        await hub.close()
