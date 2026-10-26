"""Jobs end to end: state machine, FIFO, queue limit, cancel, direct submit, retention, failure, ETA, throttle."""
from __future__ import annotations

import asyncio
import itertools
from pathlib import Path
from typing import Any

import pytest

from hub.core import jobs as jobs_mod
from hub.core.api import Ctx, Invalid, Job, JobPlan, Module, Tab
from hub.core.jobs import TRANSITIONS, Entry, JobBook, move
from tests.core.fake_lane import FakeLane
from tests.core.harness import Hub, own_modules, start_hub
from tests.fakes.fake_probes import FakeProbes

SEEN: list[dict] = []


def build(params: dict, ctx: Ctx) -> JobPlan:
    if not params.get("prompt"):
        raise Invalid("prompt", "Write a prompt")
    n = int(params.get("images", 1))
    return JobPlan(lane_kind="image", model=params.get("model", "flux"),
                   tasks=tuple({"seed": 100 + i} for i in range(n)),
                   summary={"model": "Flux", "prompt": params["prompt"]})


async def on_submitted(ctx: Ctx, data: dict) -> None:
    SEEN.append(data)


GEN = Module(id="gen", title="Gen", tab=Tab("Gen", 10), jobs={"image": build}, listens={"job.submitted": on_submitted})
STATES = list(TRANSITIONS)


@pytest.mark.parametrize("src, dst", list(itertools.product(STATES, STATES)))
def test_transition_matrix(src: str, dst: str) -> None:
    job = Job(id="j", kind="gen.image", tool="gen", state=src,  # type: ignore[arg-type]
              plan=JobPlan("image", "m", ({},), {}))
    if dst in TRANSITIONS[src]:
        move(job, dst)
        assert job.state == dst
    else:
        with pytest.raises(ValueError):
            move(job, dst)


@pytest.fixture
async def hub(tmp_path: Path):  # type: ignore[no-untyped-def]
    SEEN.clear()
    probes = FakeProbes()
    lane = FakeLane(tmp_path / "data" / "outputs", probes)
    h = await start_hub(tmp_path / "data", lanes=[lane], modules=[*own_modules(), GEN], probes=probes)
    h.lane = lane  # type: ignore[attr-defined]
    yield h
    await h.close()


async def submit(w: Any, images: int = 1, rid: str = "r1", prompt: str = "a cat") -> dict:
    await w.send("job.submit", {"tool": "gen", "kind": "image", "params": {"prompt": prompt, "images": images}}, id=rid)
    return await w.recv(where=lambda m: m.get("re") == rid)


async def test_two_images_run_through_to_done_with_generations(hub: Hub) -> None:
    cookie = hub.pair()
    w = await hub.screen(cookie, "workspace", "w")
    m = await hub.screen(cookie, "media", "m")
    r = await submit(w, images=2)
    assert r["t"] == "reply" and r["d"]["state"] == "queued"
    job_id = r["d"]["job"]
    done = await w.recv("job", where=lambda x: x["d"]["state"] == "done", timeout=5)
    gens = [await m.recv("generation") for _ in range(2)]
    assert [g["d"]["item"]["id"] for g in gens] == [f"out/2026-10-09/{job_id}_1.png", f"out/2026-10-09/{job_id}_2.png"]
    item = gens[0]["d"]["item"]
    assert item["w"] == 64 and item["h"] == 48 and item["job"] == job_id and item["kind"] == "image"
    assert "meta" not in item, "nothing about the picture travels with it"
    assert item["url"].startswith(f"/files/out/2026-10-09/{job_id}_1.png?v=")
    assert item["thumb"].startswith(f"/thumbs/out/2026-10-09/{job_id}_1.png/336?v=")
    assert done["d"]["outputs"] == [g["d"]["item"]["id"] for g in gens] and done["d"]["error"] is None
    assert done["d"]["title"] == "2 images · Flux"
    running = [x for x in w.seen if x["t"] == "job" and x["d"]["state"] == "running"]
    assert running and running[-1]["d"]["progress"]["count"] == 2
    assert SEEN == [{"job": job_id, "kind": "gen.image", "tool": "gen", "by": "screen",
                     "params": {"prompt": "a cat", "images": 2}}]
    learned = hub.core.vram.learned
    assert learned["vram"]["flux|GPU-fake-0"] == [14_000, 14_000] and "ram" not in learned
    assert not (hub.data / "core" / "learned.json").exists(), "peak needs are memory only"


async def test_a_clip_generation_has_no_thumbnail(hub: Hub) -> None:
    hub.lane.video = True  # type: ignore[attr-defined]
    cookie = hub.pair()
    w, m = await hub.screen(cookie, "workspace", "w"), await hub.screen(cookie, "media", "m")
    job_id = (await submit(w))["d"]["job"]
    done = await w.recv("job", where=lambda x: x["d"]["state"] == "done", timeout=5)
    item = (await m.recv("generation"))["d"]["item"]
    assert item["id"] == f"clips/2026-10-09/{job_id}_1.mp4" and item["kind"] == "clip"
    assert item["thumb"].startswith("/thumbs/clips/")                  # a clip's thumbnail is its first frame
    assert item["url"].startswith(f"/files/clips/2026-10-09/{job_id}_1.mp4?v=") and item["w"] is None
    assert done["d"]["outputs"] == [item["id"]]


async def test_invalid_params_and_unknown_kind(hub: Hub) -> None:
    w = await hub.screen(hub.pair(), "workspace", "w")
    r = await submit(w, prompt="")
    assert r["d"] == {"code": "invalid", "text": "Write a prompt", "field": "prompt"}
    await w.send("job.submit", {"tool": "gen", "kind": "video", "params": {}}, id="r2")
    assert (await w.recv("error"))["d"]["code"] == "not_found"


async def test_fifo_queue_limit_clear_and_cancel(hub: Hub) -> None:
    lane: FakeLane = hub.lane  # type: ignore[attr-defined]
    lane.gate = asyncio.Event()
    w = await hub.screen(hub.pair(), "workspace", "w")
    ids = [(await submit(w, rid=f"r{i}"))["d"]["job"] for i in range(11)]
    assert (await submit(w, rid="r11"))["d"] == {"code": "queue_full", "text": "Queue is full"}
    await w.recv("job", where=lambda x: x["d"]["id"] == ids[0] and x["d"]["state"] == "running")
    assert [hub.core.book.record(hub.core.book.entries[i])["position"] for i in ids[1:]] == list(range(1, 11))
    assert [hub.core.book.card(i)["position"] for i in ids[1:]] == list(range(1, 11))   # the card
    assert hub.core.book.card("gone") is None
    await w.send("job.cancel", {"job": ids[3]}, id="c1")
    assert (await w.recv("reply", where=lambda x: x["re"] == "c1"))["d"]["state"] == "cancelled"
    assert (await w.recv("job.gone"))["d"]["id"] == ids[3]
    await w.send("job.clear", {}, id="c2")
    assert (await w.recv("reply", where=lambda x: x["re"] == "c2"))["d"] == {"cleared": 9}
    await w.send("job.cancel", {"job": ids[0]}, id="c3")
    end = await w.recv("job", where=lambda x: x["d"]["id"] == ids[0] and x["d"]["state"] == "cancelled")
    assert end["d"]["cancel_requested"] is True
    assert lane.runs == [ids[0]]
    await w.send("job.cancel", {"job": "j_none"}, id="c4")
    assert (await w.recv("error"))["d"]["code"] == "not_found"


async def test_failure_is_one_line_and_retained_until_the_next_job_starts(hub: Hub) -> None:
    lane: FakeLane = hub.lane  # type: ignore[attr-defined]
    lane.fail_at = 1
    w = await hub.screen(hub.pair(), "workspace", "w")
    first = (await submit(w))["d"]["job"]
    failed = await w.recv("job", where=lambda x: x["d"]["state"] == "failed")
    assert failed["d"]["error"] == {"text": "Out of GPU memory"}
    w2 = await hub.screen(hub.pair(name="Two"), "workspace", "w2")
    assert [j["state"] for j in w2.welcome["jobs"]] == ["failed"]
    lane.fail_at = None
    await submit(w, rid="r2")
    assert (await w.recv("job.gone"))["d"]["id"] == first
    await w.recv("job", where=lambda x: x["d"]["state"] == "done")
    await w.send("job.dismiss", {"job": [k for k in hub.core.book.entries][0]}, id="d1")
    await w.recv("reply", where=lambda x: x["re"] == "d1")
    assert hub.core.book.entries == {}


async def test_a_direct_submit_queues_at_once_and_runs(hub: Hub) -> None:
    book = hub.core.book
    w = await hub.screen(hub.pair(), "workspace", "w")
    job = book.submit("gen.image", {"prompt": "from the assistant"})
    assert job.state == "queued" and job.lane is not None
    await w.recv("job", where=lambda x: x["d"]["id"] == job.id and x["d"]["state"] == "done", timeout=5)
    assert SEEN == [{"job": job.id, "kind": "gen.image", "tool": "gen", "by": "screen",
                     "params": {"prompt": "from the assistant"}}]


async def test_a_modules_submit_is_by_that_module(hub: Hub) -> None:
    """`job.submitted` names who pressed: the module whose `ctx.jobs.submit` made the job."""
    job = hub.core.ctxs["gen"].jobs.submit("image", {"prompt": "from a module"})
    for _ in range(50):
        if SEEN:
            break
        await asyncio.sleep(0.01)
    assert SEEN == [{"job": job.id, "kind": "gen.image", "tool": "gen", "by": "gen",
                     "params": {"prompt": "from a module"}}]


async def test_engine_offline_keeps_the_job_queued_until_start(hub: Hub) -> None:
    lane: FakeLane = hub.lane  # type: ignore[attr-defined]
    lane.is_ready = False
    w = await hub.screen(hub.pair(), "workspace", "w")
    job = (await submit(w))["d"]["job"]
    await asyncio.sleep(0.3)
    assert hub.core.book.entries[job].job.state == "queued"
    assert w.welcome["presence"]["engines"] == {"image.gpu0": "down"}
    await w.send("engine.start", {}, id="go")
    await w.recv("job", where=lambda x: x["d"]["state"] == "done", timeout=5)


class RecordingBus:
    def __init__(self) -> None:
        self.sent: list[tuple[float, dict, bool]] = []

    def publish(self, lane: str, t: str, d: dict, key: str | None = None, replace: bool = True) -> None:
        self.sent.append((asyncio.get_running_loop().time(), d, replace))


async def test_progress_is_throttled_to_four_a_second_but_state_changes_are_not() -> None:
    bus = RecordingBus()
    book = JobBook(bus, lambda: {"queue": {"max_waiting": 10}}, lambda e, d: None)  # type: ignore[arg-type]
    e = Entry(Job("j_1", "gen.image", "gen", "running", JobPlan("image", "m", ({},), {})), {})
    book.entries["j_1"] = e
    for _ in range(100):
        book.publish(e, progress_only=True)
        await asyncio.sleep(0.01)
    book.publish(e)
    await asyncio.sleep(0.3)
    progress = [t for t, _, replace in bus.sent if replace]
    assert len([x for x in bus.sent if not x[2]]) == 1
    span = progress[-1] - progress[0]
    assert len(progress) <= span / jobs_mod.PUBLISH_GAP_S + 2


async def test_eta_uses_measured_seconds_per_step_and_skips_loading(hub: Hub) -> None:
    clock = iter([0.0, 0.0, 10.0, 12.0, 14.0, 100.0, 102.0])
    hub.core.dispatch.clock = lambda: next(clock)
    e = Entry(Job("j_e", "gen.image", "gen", "running", JobPlan("image", "m", ({}, {}), {})), {})
    hub.core.book.entries["j_e"] = e
    lane = hub.lane  # type: ignore[attr-defined]
    expected = [None, None, 60.0, 30.0, 18.7, 14.0, 8.0]
    steps = [(1, "loading_model", 1), (1, "inference", 1), (1, "inference", 2), (1, "inference", 3),
             (1, "inference", 4), (2, "inference", 1), (2, "inference", 2)]
    for (task, phase, step), eta in zip(steps, expected, strict=True):
        hub.core.dispatch._event(lane, e, "progress", {"task": task, "phase": phase, "step": step, "steps": 4})
        assert e.job.eta_s == eta, (task, step)
    assert e.job.pct == 75 and e.job.task == 2


async def test_shutdown_stops_a_busy_lane_instead_of_asking_it_to_release(hub: Hub) -> None:
    lane: FakeLane = hub.lane  # type: ignore[attr-defined]
    lane.gate = asyncio.Event()
    w = await hub.screen(hub.pair(), "workspace", "w")
    job = (await submit(w))["d"]["job"]
    await w.recv("job", where=lambda x: x["d"]["id"] == job and x["d"]["state"] == "running")
    await hub.core.stop(restart=False)
    assert lane.released == ["stop"]
    lane.gate.set()


async def test_notes_carry_what_the_hub_learns_after_submit_and_refuse_fails_a_queued_job(hub: Hub) -> None:
    """`note` merges into the job's `notes` and publishes the card; a judge's verdict in `task_done` lands under
    `notes["judged"]` by task; `job.finished` carries the notes; `refuse` fails a queued job with one line."""
    lane: FakeLane = hub.lane  # type: ignore[attr-defined]
    lane.judge = {"words": {"heard": 0.93, "first_miss": None}}
    lane.gate = asyncio.Event()
    w = await hub.screen(hub.pair(), "workspace", "w")
    first = (await submit(w, images=2))["d"]["job"]
    second = (await submit(w, rid="r2"))["d"]["job"]
    book = hub.core.book
    assert book.note(first, plan={"windows": 1}).notes == {"plan": {"windows": 1}}
    card = await w.recv("job", where=lambda x: x["d"]["id"] == first and x["d"].get("notes", {}).get("plan"))
    assert card["d"]["notes"] == {"plan": {"windows": 1}}
    assert book.refuse(second, "Cut 2 at 7.0 s is inside window 1").state == "failed"
    gone = await w.recv("job", where=lambda x: x["d"]["id"] == second and x["d"]["state"] == "failed")
    assert gone["d"]["error"] == {"text": "Cut 2 at 7.0 s is inside window 1"}
    assert book.note("j_none", plan={}) is None and book.refuse("j_none", "x") is None
    lane.gate.set()
    done = await w.recv("job", where=lambda x: x["d"]["id"] == first and x["d"]["state"] == "done")
    assert done["d"]["notes"] == {"plan": {"windows": 1}, "judged": {"1": lane.judge, "2": lane.judge}}
    assert book.refuse(first, "too late").state == "done", "a job that is over is left as it is"
