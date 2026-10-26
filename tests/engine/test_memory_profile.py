"""The engine's memory profile: the profile set reaches the engine config the worker seeds (under every key the engine
reads it from), the engine's own stays when none is picked, and a change stops the worker so its next start uses it.
The video profile: a job on a video model runs with it. Residency: the lane knows the model its worker holds and frees
it (the release "Clear the GPU cache" sends) before a job on another model, never before one on the same."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from hub.core import api, engine, enginecat
from hub.core.engine import EngineLane
from hub.core.supervisor import job_profile, worker_args
from hub.settings import DEFAULTS, SAME
from hub.worker import wgpconfig
from tests.core.harness import own_modules, start_hub
from tests.engine.helpers import ENGINE_PYTHON, WORKER, clip_task, make_engine_root, task
from tests.engine.test_engine_lane import Events, Probes, job, settings
from tests.engine.test_settings_live import _engine_hub
from tests.fakes.fake_probes import FakeProbes
from tests.fakes.mp4 import tiny_mp4

OWN = {"profile": 2, "video_profile": 3, "image_profile": 2, "audio_profile": 3.5}


def seeded(tmp_path: Path, profile: float | None, own: dict | None = None) -> dict:
    root = tmp_path / "engine"
    root.mkdir(exist_ok=True)
    (root / "wgp_config.json").write_text(json.dumps({"last_model_type": "x", **(own or {})}))
    path = wgpconfig.seed_config(str(root), str(tmp_path / "config"), str(tmp_path / "out"), [], profile)
    return json.loads(Path(path).read_text())


@pytest.mark.parametrize(("profile", "written"), [(5.0, 5), (3.5, 3.5), (1.0, 1)])
def test_a_picked_profile_is_written_under_every_key_the_engine_reads(tmp_path, profile, written):
    config = seeded(tmp_path, profile, OWN)
    assert {k: config[k] for k in wgpconfig.PROFILE_KEYS} == dict.fromkeys(wgpconfig.PROFILE_KEYS, written)
    assert type(config["profile"]) is type(written), "a whole profile is written whole"
    assert config["audio_profile"] == 3.5 and config["last_model_type"] == "x", "the rest is the engine's"


def test_no_pick_leaves_the_engine_configs_own(tmp_path):
    assert {k: seeded(tmp_path, None, OWN)[k] for k in OWN} == OWN
    assert not set(wgpconfig.PROFILE_KEYS) & set(seeded(tmp_path, None)), "absent stays absent: the engine's default"


def test_the_worker_is_told_only_a_picked_profile(tmp_path):
    engine = {"root": "/e", "args": ["--fast"], "model_folders": ["/m"], "profile": "engine"}
    assert worker_args(engine, tmp_path) == ("--root", "/e", "--state", str(tmp_path), "--models", "/m", "--",
                                             "--fast")
    args = worker_args({**engine, "profile": 3.5}, tmp_path)
    assert args[args.index("--profile") + 1] == "3.5" and args.index("--profile") < args.index("--")
    assert worker_args({**engine, "profile": 5}, tmp_path)[-4:] == ("--profile", "5", "--", "--fast")


def test_the_worker_seeds_the_profile_it_is_given(tmp_path):
    root = make_engine_root(tmp_path, "legacy")
    state = tmp_path / "state"
    subprocess.run([ENGINE_PYTHON, "-B", str(WORKER), "--root", str(root), "--state", str(state), "--profile", "4.5",
                    "--dump-catalog", str(tmp_path / "catalog.json")], check=True, capture_output=True, timeout=60)
    config = json.loads((state / "config" / "wgp_config.json").read_text())
    assert config["profile"] == config["video_profile"] == config["image_profile"] == 4.5
    assert "profile" not in json.loads((root / "wgp_config.json").read_text()), "the engine root is never written"


async def test_a_new_profile_stops_the_worker_so_its_next_start_uses_it(tmp_path):
    _, lane, hub = await _engine_hub(tmp_path)
    try:
        cookie = hub.pair()
        await lane.sup.start()
        assert lane.sup.pid is not None and "--profile" not in lane.sup.spawn.args
        r = await hub.http("PATCH", "/api/settings", cookie, json_body={"engine": {"profile": 5}})
        assert r.status == 200 and r.json()["engine"]["profile"] == 5
        assert lane.sup.pid is None, "stopped: the next job starts it with the new profile"
        args = lane.sup.spawn.args
        assert args[args.index("--profile") + 1] == "5"
        await hub.http("PATCH", "/api/settings", cookie, json_body={"engine": {"profile": "engine"}})
        assert "--profile" not in lane.sup.spawn.args
    finally:
        await hub.close()
        await lane.stop()


def test_a_video_job_takes_the_video_profile_unless_it_follows_the_general_one():
    engine = {"profile": 2, "profile_video": SAME}
    assert [job_profile(engine, kind) for kind in ("image", "video", None)] == [2, 2, 2]
    engine["profile_video"] = 4.5
    assert [job_profile(engine, kind) for kind in ("image", "video", None)] == [2, 4.5, 2], "unknown: the general"
    assert job_profile({"profile": "engine", "profile_video": 5}, "video") == 5
    assert job_profile({"profile": 5, "profile_video": "engine"}, "video") == "engine", "the engine's own is a choice"
    assert worker_args({**engine, "root": "/e"}, Path("/s"), 4.5)[-3:] == ("--profile", "4.5", "--")


def profile_of(lane) -> str | None:
    args = lane.sup.spawn.args
    return args[args.index("--profile") + 1] if "--profile" in args else None


async def test_each_job_runs_with_the_profile_of_its_models_kind(tmp_path):
    """The worker a job runs on has the profile its model's kind wants. A clip's worker is stopped when it ends (its
    memory goes back at once), so the profile is checked while each job runs."""
    _, lane, hub = await _engine_hub(tmp_path)
    try:
        cookie = hub.pair()
        cat = await lane.query("models")
        clip = next(m["id"] for m in cat["models"] if m["kind"] == "video")
        n = iter(range(100))

        async def run(model: str) -> tuple[int | None, str | None]:   # the worker's pid and profile during the job
            seen: list[tuple[int | None, str | None]] = []
            one = api.Job(id=f"j_{next(n)}", kind="generate-image.image", tool="generate-image", state="running",
                          plan=api.JobPlan("image", model, (task(),), {}))
            await lane.run(one, lambda ev, d: seen.append((lane.sup.pid, profile_of(lane))) if ev == "task" else None)
            return seen[0]

        image, profile = await run("flux2_klein_9b")
        assert image is not None and profile is None
        assert await run("flux2_klein_9b") == (image, None), "the same model: the same worker"
        video, profile = await run(clip)
        assert video not in (None, image) and profile is None, "SAME: the general profile, in a fresh worker"
        assert lane.sup.pid is None, "the clip's worker is stopped when it ends"
        image, _ = await run("flux2_klein_9b")
        r = await hub.http("PATCH", "/api/settings", cookie, json_body={"engine": {"profile_video": 4}})
        assert r.status == 200 and r.json()["engine"]["profile_video"] == 4
        assert lane.sup.pid == image, "a new video profile restarts nothing until a video job"
        assert await run("flux2_klein_9b") == (image, None), "an image job: the general profile, which it has"
        assert (await run(clip))[1] == "4" and (await run(clip))[1] == "4"
        assert (await run("flux2_klein_9b"))[1] is None
        await hub.http("PATCH", "/api/settings", cookie, json_body={"engine": {"profile": 4}})
        assert lane.sup.pid is None, "the general profile still stops the worker at once"
        assert (await run("flux2_klein_9b"))[1] == "4" and (await run(clip))[1] == "4", "both 4"
        await hub.http("PATCH", "/api/settings", cookie, json_body={"engine": {"profile_video": "same"}})
        assert (await run(clip))[1] == "4" and (await run("flux2_klein_9b"))[1] == "4"
        bad = await hub.http("PATCH", "/api/settings", cookie, json_body={"engine": {"profile_video": 7}})
        assert bad.status == 400 and bad.json()["field"] == "engine.profile_video"
    finally:
        await hub.close()
        await lane.stop()


def recorded_lane(tmp_path: Path, flavour: str = "upstream") -> tuple[EngineLane, Path]:
    """A lane on the fake engine that keeps its record (`fake_gpu`): one line per worker start, model load and the
    engine's own release, in order across worker restarts."""
    data = tmp_path / "data"
    lane, _ = engine.create(settings(make_engine_root(tmp_path, flavour), uuid="GPU-fake-0"), data, Probes(None))
    record = data / "engine" / "gpu0" / "config" / "fake_engine_record.txt"
    record.parent.mkdir(parents=True, exist_ok=True)
    record.touch()
    return lane, record


def lines(record: Path) -> list[str]:
    return record.read_text().splitlines()


@pytest.mark.parametrize("flavour", ["legacy", "upstream"])
async def test_another_model_is_released_before_it_loads_and_the_same_model_never(tmp_path, flavour):
    lane, record = recorded_lane(tmp_path, flavour)
    try:
        assert lane.held() is None and lane._resident is None
        await lane.run(job(task(), job_id="j_1"), Events())
        pid = lane.sup.pid
        assert lane.held() == lane._resident == "flux2_klein_9b", "the last task's model, held by the running worker"
        same = Events()
        await lane.run(job(task(seed=2), job_id="j_2"), same)
        assert lane.sup.pid == pid and not [d for d in same.of("model") if d["state"] == "released"]
        assert lines(record) == ["start", "load flux2_klein_9b"], "the same model: no release, no reload"
        other = Events()
        await lane.run(job(task("z_image"), job_id="j_3"), other)
        assert lane.sup.pid not in (None, pid) and lane.held() == "z_image"
        assert other[0] == ("model", {"state": "released", "model": "flux2_klein_9b"}), "released before it starts"
        assert lines(record) == ["start", "load flux2_klein_9b", "start", "load z_image"], \
            "the worker was stopped and a fresh one loaded the new model: the engine never swapped in place"
        await lane.release("owner")
        assert lane.held() is None and lane._resident is None and lane.residency() == []
    finally:
        await lane.stop()


async def test_a_crash_forgets_the_resident_model(tmp_path):
    lane, record = recorded_lane(tmp_path)
    try:
        await lane.run(job(task(), job_id="j_1"), Events())
        with pytest.raises(engine.EngineFailed):
            await lane.run(job(task(prompt="CRASH"), job_id="j_2"), Events())
        assert lane._resident is None and lane.held() is None
        await lane.run(job(task("z_image"), job_id="j_3"), Events())
        assert lines(record) == ["start", "load flux2_klein_9b", "start", "load z_image"]
    finally:
        await lane.stop()


def readable_clips(monkeypatch) -> None:
    """The fake engine's stand-in clip becomes one the hub can read as it lands."""
    real = enginecat.land

    def land(src: str, *roots: Path) -> dict:
        if src.endswith(".mp4"):
            Path(src).write_bytes(tiny_mp4())
        return real(src, *roots)
    monkeypatch.setattr(enginecat, "land", land)


CLIPS = api.Module(id="clips", title="Clips", tab=api.Tab("Clips", 90), jobs={"clip": lambda params, ctx: api.JobPlan(
    "image", "minimax_h3", (clip_task("minimax_h3", steps=3),), {"model": "Clip"})})


async def test_a_clips_peak_reaches_the_per_model_need(tmp_path, monkeypatch):
    """The worker's peak for a video task travels in `task_done` (wan2gp `Peaks` -> engine `_task` -> dispatch
    `_ev_task_done`) to the per-model need the plan reads, though the worker is stopped right after."""
    readable_clips(monkeypatch)
    s = {"engine": {"python": sys.executable, "root": str(make_engine_root(tmp_path)), "args": [], "model_folders": []},
         "gpus": [{"id": "gpu0", "index": 0, "uuid": "GPU-fake-0", "engine": True}]}
    probes = FakeProbes()
    lane, _ = engine.create({**DEFAULTS, **s}, tmp_path / "data", probes)
    hub = await start_hub(tmp_path / "data", lanes=[lane], modules=[*own_modules(), CLIPS], probes=probes, settings=s)
    try:
        w = await hub.screen(hub.pair(), "workspace", "w")
        await w.send("job.submit", {"tool": "clips", "kind": "clip", "params": {}}, id="r1")
        done = await w.recv("job", where=lambda m: m["d"]["state"] in ("done", "failed"), timeout=30)
        assert done["d"]["state"] == "done", done
        assert hub.core.vram.need("vram", "minimax_h3", "GPU-fake-0") == 400 + 20_000, "fake_gpu: context + clip"
        assert lane.sup.pid is None and lane.residency() == []
    finally:
        await hub.close()
        await lane.stop()
