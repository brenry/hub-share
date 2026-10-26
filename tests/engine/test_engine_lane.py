"""EngineLane (api.JobLane + api.Engine) built by `engine.create`, running the real worker on the fake engine."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from hub.core import api, engine, supervisor
from hub.core.engine import EngineFailed, EngineLane
from hub.core.supervisor import Spawn, worker_env
from tests.engine.helpers import ENGINE_PYTHON, FAKE_WORKER, make_engine_root, snapshot, task


class Probes:
    def __init__(self, gpus: list[dict] | None) -> None:
        self._gpus = gpus

    def gpus(self) -> list[dict] | None:
        return self._gpus


def settings(root: Path, python: str = ENGINE_PYTHON, uuid: str | None = "GPU-aaaa") -> dict:
    return {"engine": {"python": python, "root": str(root), "args": ["--profile", "4"], "model_folders": []},
            "gpus": [{"id": "gpu0", "index": 0, "uuid": uuid, "engine": True}], "diagnostics": False}


def job(*tasks: dict, job_id: str = "j_1") -> api.Job:
    return api.Job(id=job_id, kind="generate-image.image", tool="generate-image", state="running",
                   plan=api.JobPlan("image", tasks[0]["model"], tasks, {"model": "Flux 2 Klein 9B"}))


class Events(list):
    def __call__(self, event: str, data: dict) -> None:
        self.append((event, data))

    def of(self, kind: str) -> list[dict]:
        return [d for e, d in self if e == kind]


@pytest.fixture(autouse=True)
def quick_backoff(monkeypatch):
    monkeypatch.setattr(supervisor, "BACKOFF_S", (0.05, 0.1, 0.2))


@pytest.fixture(params=("legacy", "upstream"))
def lane(request, tmp_path):
    root = make_engine_root(tmp_path, request.param)
    data = tmp_path / "data"
    lane, eng = engine.create(settings(root), data, Probes(None))
    assert lane is eng and isinstance(lane, EngineLane)
    lane.root, lane.data = root, data
    yield lane


async def test_run_lands_images_in_the_library(lane):
    changes: list[int] = []
    lane.on_change = lambda: changes.append(1)
    before = snapshot(lane.root)
    ev = Events()
    await lane.run(job(task(seed=1), task(seed=2)), ev)
    assert [d["task"] for d in ev.of("task")] == [1, 2] and ev.of("task")[0]["of"] == 2
    assert ev.of("model")[0] == {"state": "loading", "model": "flux2_klein_9b"}
    outputs = ev.of("output")
    items = [d["item"] for d in outputs]
    assert len(items) == 2 and all(i.startswith("out/") and i.endswith(".png") for i in items)
    assert all("flux" not in i and "seed" not in i for i in items), "the name is the time, nothing else"
    assert all((d["w"], d["h"]) == (64, 48) for d in outputs), "the size travels with the event"
    for item in items:
        assert (lane.data / "outputs" / item[4:]).is_file()
    assert not any((lane.data / "engine" / "gpu0" / "outbox").iterdir())
    pcts = [d["pct"] for d in ev.of("progress")]
    assert pcts == sorted(pcts) and pcts[-1] == 100
    done = ev.of("task_done")
    assert len(done) == 2 and done[0]["model"] == "flux2_klein_9b" and done[0]["peak_rss_mb"] > 0
    assert lane.residency() == [api.Resident("flux2_klein_9b")] and not lane.busy() and lane.ready()
    assert lane.pids() and changes
    assert await lane.release("idle") is True
    assert lane.residency() == [] and lane.pids() == []
    assert snapshot(lane.root) == before


async def test_models_query_uses_the_catalog_cache(lane, tmp_path):
    first = await lane.query("models")
    assert {m["id"] for m in first["models"]} >= {"flux2_klein_9b", "z_image"} and first["resident"] is None
    assert lane.sup.state == "none", "a worker started only for the catalog is stopped again"
    assert (lane.data / "engine" / "catalog.json").is_file()
    again, _ = engine.create(settings(lane.root), lane.data, Probes(None))
    assert (await again.query("models"))["models"] == first["models"]
    assert again.sup.pid is None, "the cached catalog needs no worker"
    assert (await again.query("models", rescan=True))["models"] == first["models"]
    assert again.sup.state == "none", "a rescan asks the engine again (worker started and stopped)"
    with pytest.raises(ValueError):
        await lane.query("loras")


async def test_catalog_queries_at_once_share_one_worker(lane):
    """The screen's warm-up and a first GET /models arrive together: one worker start, both answered, and neither
    stops the worker the other is still asking. Rescans asked together share one fetch too."""
    spawns: list[int] = []
    spawn = lane.sup._spawn

    async def counted() -> None:
        spawns.append(1)
        await spawn()
    lane.sup._spawn = counted
    first, second = await asyncio.gather(lane.query("models"), lane.query("models"))
    assert first["models"] == second["models"] and {m["id"] for m in first["models"]} >= {"flux2_klein_9b"}
    assert (len(spawns), lane._fetches, lane.sup.state) == (1, 1, "none"), "one worker, one fetch, stopped again"
    panels = await asyncio.gather(*(lane.query("weights", rescan=True) for _ in range(3)))
    assert (len(spawns), lane._fetches, lane.sup.state) == (2, 2, "none") and panels[0] == panels[1] == panels[2]


async def test_cancel_stops_after_the_current_image(lane):
    ev = Events()

    def emit(event: str, data: dict) -> None:
        ev(event, data)
        if event == "progress" and data.get("phase") == "inference":

            asyncio.get_running_loop().create_task(lane.cancel("j_1"))

    with pytest.raises(EngineFailed) as err:
        await lane.run(job(task(prompt="SLOW", steps=30), task()), emit)
    assert err.value.stage == "cancelled" and len(ev.of("task")) == 1 and not ev.of("output")
    await lane.release("test")


async def test_engine_failure_is_one_line(lane):
    with pytest.raises(EngineFailed) as err:
        await lane.run(job(task(prompt="OOM")), Events())
    assert (err.value.stage, err.value.text) == ("oom", "Out of GPU memory")
    await lane.run(job(task(), job_id="j_2"), Events())
    await lane.release("test")


async def test_a_request_the_worker_would_refuse_never_reaches_it(lane):
    """Review 16: each plan task is parsed as the worker will parse it before the worker is started or sent it."""
    bad = {**task(), "references": [{"path": "/a.png", "role": "start", "name": None, "cutout": False}]}
    with pytest.raises(EngineFailed) as err:
        await lane.run(job(task(), bad), Events())
    assert (err.value.stage, err.value.text) == (
        "runtime", "Task 2 is not a request the engine takes: request.references[0]: a picture request takes no "
                   "start picture")
    assert lane.sup.pid is None and lane.sup.state == "none", "the worker was never started for it"
    odd = {**task(), "kind": "audio"}
    with pytest.raises(EngineFailed, match="unknown kind 'audio'"):
        await lane.run(job(odd, job_id="j_2"), Events())


async def test_crash_fails_the_job_and_the_next_one_restarts(lane):
    changes: list[int] = []
    lane.on_change = lambda: changes.append(1)
    await lane.run(job(task()), Events())
    with pytest.raises(EngineFailed) as err:
        await lane.run(job(task(prompt="CRASH"), job_id="j_2"), Events())
    assert err.value.stage == "crashed" and "exit code 139" in err.value.text
    assert lane.residency() == [] and lane.pids() == [] and lane.ready()
    await lane.run(job(task(), job_id="j_3"), Events())
    assert lane.residency()
    await lane.stop()
    assert lane.residency() == []


async def test_release_is_refused_while_a_job_runs(tmp_path):
    lane = EngineLane("image.gpu0", None, Spawn(sys.executable, ("--root", str(tmp_path), "--state",
                      str(tmp_path / "s"), "--", "slow"), worker_env(tmp_path / "h", "0"), tmp_path / "w.pid",
                      FAKE_WORKER), tmp_path, tmp_path / "s", "key")

    running = asyncio.create_task(lane.run(job(task("fake_model", steps=3)), Events()))
    while not lane.busy():
        await asyncio.sleep(0.01)
    assert await lane.release("make room") is False
    await running
    assert await lane.release("make room") is True


async def test_create_without_engine_paths_is_down(tmp_path):
    lane, _ = engine.create(settings(tmp_path / "missing", python=str(tmp_path / "nope")), tmp_path, Probes(None))
    assert not lane.ready()
    with pytest.raises(EngineFailed) as err:
        await lane.run(job(task()), Events())
    assert "run hub init" in err.value.text
    with pytest.raises(EngineFailed):
        await lane.query("models")


def test_create_pins_the_gpu_by_uuid(tmp_path):
    root = make_engine_root(tmp_path)
    lane, _ = engine.create(settings(root, uuid=None), tmp_path, Probes([{"index": 0, "uuid": "GPU-from-nvml"}]))
    assert lane.id == "image.gpu0" and lane.gpu_uuid == "GPU-from-nvml"
    assert lane.sup.spawn.env["CUDA_VISIBLE_DEVICES"] == "GPU-from-nvml"
    lane, _ = engine.create(settings(root, uuid=None), tmp_path, Probes(None))
    assert lane.gpu_uuid is None and lane.sup.spawn.env["CUDA_VISIBLE_DEVICES"] == "0"
    s = settings(root)
    s["gpus"] = [{"id": "gpu1", "index": 1, "uuid": "GPU-b", "engine": True}, *s["gpus"]]
    lane, _ = engine.create(s, tmp_path, Probes(None))
    assert lane.id == "image.gpu1" and lane.sup.spawn.pidfile == tmp_path / "run" / "worker-gpu1.pid"


def test_catalog_key_follows_engine_changes(tmp_path):
    root = make_engine_root(tmp_path)
    eng = settings(root)["engine"]
    key = engine.catalog_key(eng)
    assert engine.catalog_key(eng) == key
    (root / "finetunes").mkdir()
    assert engine.catalog_key(eng) != key
    key = engine.catalog_key(eng)
    (root / "ckpts").mkdir()
    assert engine.catalog_key(eng) != key, "new weights may make a model available"
    assert engine.catalog_key({**eng, "args": ["--profile", "3"]}) != engine.catalog_key(eng)


def test_the_catalog_key_watches_what_the_roots_adapter_names(tmp_path):
    """The entries come from the adapter that drives the root (`Adapter.pointers.watch`); a root none drives keeps a
    key from the settings alone."""
    from hub.core import enginecat
    from hub.worker.adapters import pointers

    root = make_engine_root(tmp_path)
    assert enginecat.watched(str(root)) == [root / name for name in pointers.WATCH]
    assert enginecat.watched(str(tmp_path / "nothing")) == [] and enginecat.watched("") == []
    eng = {**settings(root)["engine"], "root": str(tmp_path / "nothing")}
    assert engine.catalog_key(eng) == engine.catalog_key(eng)


async def test_a_cancel_that_comes_while_the_lane_is_releasing_is_kept(tmp_path: Path) -> None:
    """The dispatcher may start a job while release() still stops the worker; its cancel must not be lost."""
    lane = EngineLane("image.gpu0", None, Spawn(sys.executable, ("--root", str(tmp_path), "--state",
                      str(tmp_path / "s"), "--", "ignore-stop"), worker_env(tmp_path / "h", "0"),
                      tmp_path / "w.pid", FAKE_WORKER), tmp_path, tmp_path / "s", "key")
    lane.sup.stop_grace, lane.sup.term_grace = 0.6, 0.2
    one = task("fake_model", steps=2)
    await lane.run(job(one, job_id="j_0"), Events())
    releasing = asyncio.create_task(lane.release("idle"))
    await asyncio.sleep(0.05)
    assert lane._lock.locked() and not lane.busy()
    events = Events()
    running = asyncio.create_task(lane.run(job(one, one, one, job_id="j_1"), events))
    await asyncio.sleep(0.05)
    await lane.cancel("j_1")
    await releasing
    with pytest.raises(EngineFailed) as failed:
        await running
    assert failed.value.stage == "cancelled" and events.of("output") == [] and lane.sup.pid is None
    await lane.release("test")


def test_create_removes_a_config_left_half_written(tmp_path: Path) -> None:
    stale = tmp_path / "data" / "engine" / "gpu0" / "config" / "wgp_config.json.tmp"
    stale.parent.mkdir(parents=True)
    stale.write_text("{")
    engine.create(settings(make_engine_root(tmp_path)), tmp_path / "data", Probes(None))
    assert not stale.exists()


def test_landing_cuts_whatever_the_engine_wrote_into_the_file(tmp_path: Path) -> None:
    """Even an engine that ignores `metadata_type` lands a plain picture: the hub cuts the metadata itself."""
    from PIL import Image, PngImagePlugin

    from hub.core import enginecat
    outbox, outputs = tmp_path / "outbox", tmp_path / "outputs"
    outbox.mkdir()
    outputs.mkdir()
    info = PngImagePlugin.PngInfo()
    info.add_text("prompt", "a grey cat asleep under an apple tree")
    info.add_itxt("comment", '{"seed": 1234}')
    Image.new("RGB", (6, 4), (9, 8, 7)).save(outbox / "2026-10-12-1234.png", "PNG", pnginfo=info)
    got = enginecat.land(str(outbox / "2026-10-12-1234.png"), outbox, outputs)
    item, w, h = got["id"], got["w"], got["h"]
    assert (w, h) == (6, 4) and not list(outbox.iterdir())
    landed = outputs / item[4:]
    raw = landed.read_bytes()
    assert b"grey cat" not in raw and b"1234" not in raw and b"tEXt" not in raw and b"iTXt" not in raw
    with Image.open(landed) as im:
        assert im.getpixel((0, 0)) == (9, 8, 7) and "prompt" not in im.info
