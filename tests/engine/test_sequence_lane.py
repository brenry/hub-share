"""A job that loads no model (`api.NO_MODEL`, a join) on the engine lane: the plan runs it at once and releases
nothing, the lane keeps its worker and the model it holds, no kind is looked up for it, no unload follows it, and no
VRAM need is learned from it. The worker's join itself is the worker's (`hub/worker/join.py`): here the lane's run op
for it is answered as the worker answers (a `task_done` with the model the engine holds)."""
from __future__ import annotations

import asyncio

from hub.core import api
from hub.core.plan import Plan, Situation, decide
from tests.core.fake_lane import FakeLane
from tests.core.harness import start_hub
from tests.engine.helpers import task
from tests.engine.test_engine_lane import Events, job
from tests.engine.test_memory_profile import lines, recorded_lane
from tests.fakes.fake_probes import FakeProbes

REQUEST = {"items": [], "canvas": {"w": 960, "h": 544, "fps": 24.0}, "audio": [], "crf": 18, "preset": "medium"}
JOIN = {"kind": "join", **REQUEST}


def join_job(job_id: str = "s_1") -> api.Job:
    return api.Job(id=job_id, kind="sequence.join", tool="sequence", state="running",
                   plan=api.JobPlan("image", api.NO_MODEL, (JOIN,), {"kind": "clip", "mode": "join"}))


def test_the_plan_runs_a_join_at_once_and_releases_nothing() -> None:
    for resident in ((), ("flux2_klein_9b",)):
        for need in (None, 20_000):
            plan = decide(Situation(lane="image.gpu0", model=api.NO_MODEL, label="", resident=resident, need=need))
            assert plan == Plan("green", "run", "Joining clips") and plan.release == ()


def answer_joins(lane, sent: list[dict]) -> None:  # type: ignore[no-untyped-def]
    """The worker's side of a join, as it answers one: no model loaded, the one it holds reported."""
    real = lane.sup.send

    async def send(msg: dict) -> None:
        if msg.get("op") == "run" and (msg.get("request") or {}).get("kind") == "join":
            sent.append(msg)
            done = {"ev": "task_done", "job": msg["job"], "task": msg["task"], "ok": True, "seconds": 0.5,
                    "model": lane._model, "peak_vram_mb": 900, "peak_rss_mb": 300}
            asyncio.get_running_loop().call_soon(lane._on_event, done)
            return
        await real(msg)
    lane.sup.send = send


async def test_a_join_keeps_the_resident_picture_model_and_its_worker(tmp_path):
    lane, record = recorded_lane(tmp_path)
    try:
        await lane.run(job(task(), job_id="j_1"), Events())
        pid = lane.sup.pid
        assert lane.held() == "flux2_klein_9b" and lines(record) == ["start", "load flux2_klein_9b"]
        sent: list[dict] = []
        answer_joins(lane, sent)
        assert await lane._kind(join_job()) is None, "no catalog entry and no image_mode: no kind"
        ev = Events()
        await lane.run(join_job(), ev)
        assert [m["request"] for m in sent] == [{"kind": "join", **REQUEST}], "sent as op run with its request"
        assert not ev.of("model"), "nothing released, nothing loaded"
        assert ev.of("task_done") == [{"task": 1, "seconds": 0.5, "model": "flux2_klein_9b", "peak_vram_mb": 900,
                                       "peak_rss_mb": 300}]
        assert (lane.sup.pid, lane.held(), lane._resident) == (pid, "flux2_klein_9b", "flux2_klein_9b")
        assert lane.residency() == [api.Resident("flux2_klein_9b")] and not lane.busy()
        await lane._after(join_job(), None, ev)
        assert lane.sup.pid == pid, "_after skips a job of no kind"
        again = Events()
        await lane.run(job(task(seed=2), job_id="j_2"), again)
        assert lane.sup.pid == pid and not [d for d in again.of("model") if d["state"] == "released"]
        assert lines(record) == ["start", "load flux2_klein_9b"], "the picture job after it: no release, no load"
    finally:
        await lane.stop()


async def test_a_join_learns_no_need_and_releases_no_model(tmp_path):
    """Through the dispatcher: a picture model is resident; the join runs on the lane without a release, and its
    peak is not learned for any model."""
    probes = FakeProbes()
    lane = FakeLane(tmp_path / "data" / "outputs", probes)
    plans = {"image": lambda p, ctx: api.JobPlan("image", "flux", ({},), {"model": "Flux"}),
             "join": lambda p, ctx: api.JobPlan("image", api.NO_MODEL, (JOIN,), {"mode": "join"})}
    mod = api.Module(id="seq-test", title="T", jobs=plans)
    hub = await start_hub(tmp_path / "data", lanes=[lane], modules=[mod], probes=probes)
    try:
        for kind in ("image", "join"):
            j = hub.core.book.submit(f"seq-test.{kind}", {})
            for _ in range(200):
                if j.state in ("done", "failed"):
                    break
                await asyncio.sleep(0.02)
            assert j.state == "done", (kind, j.error)
        assert lane.released == [], "the join never released the picture model"
        assert hub.core.vram.need("vram", "flux", lane.gpu_uuid) is not None, "the picture job's need is learned"
        assert hub.core.vram.need("vram", api.NO_MODEL, lane.gpu_uuid) is None, "the join's is not"
        assert set(hub.core.vram.learned["vram"]) == {f"flux|{lane.gpu_uuid}"}
    finally:
        await hub.close()


async def test_a_join_that_started_the_worker_stops_it_when_no_model_is_held(tmp_path):
    lane, record = recorded_lane(tmp_path)
    try:
        sent: list[dict] = []
        answer_joins(lane, sent)
        ev = Events()
        await lane.run(join_job(), ev)
        assert len(sent) == 1 and ev.of("task_done"), "the join ran on a worker it started"
        assert lane.sup.pid is None and lane.held() is None, "and that worker, holding nothing, is stopped after it"
        assert lines(record) == ["start"] and not ev.of("model"), "no model loaded, none to release"
        await lane.run(join_job("s_2"), Events())
        await lane.run(job(task(), job_id="j_1"), Events())
        held = lane.sup.pid
        await lane.run(join_job("s_3"), Events())
        assert (lane.sup.pid, lane.held()) == (held, "flux2_klein_9b"), "a worker up with a model keeps it"
    finally:
        await lane.stop()


async def test_a_join_does_not_follow_the_profile(tmp_path, monkeypatch):
    lane, _ = recorded_lane(tmp_path)
    followed: list[str | None] = []
    real = lane._follow_profile

    async def follow(kind: str | None) -> None:
        followed.append(kind)
        await real(kind)
    monkeypatch.setattr(lane, "_follow_profile", follow)
    try:
        answer_joins(lane, [])
        await lane.run(join_job(), Events())
        assert followed == [], "a job that loads no model keeps the worker's profile"
        await lane.run(job(task(), job_id="j_1"), Events())
        assert len(followed) == 1, "a picture job follows its kind's"
    finally:
        await lane.stop()
