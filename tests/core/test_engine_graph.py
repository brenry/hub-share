"""A job of ordered steps on the real engine lane and dispatcher, a fake worker behind them : step
2 is sent step 1's landed file; step 1's file stays off the job's outputs and Media while the job runs, is erased when
it is done, and becomes the job's output when a later step fails (`Voice step: …`). A job without inputs reports
exactly the recorded events, jobs and messages of `GOLDEN`."""
from __future__ import annotations

import asyncio
import copy
import itertools
import json
import re
from pathlib import Path
from typing import Any

from hub.core import api, jobs
from hub.core.dispatch import Dispatcher
from hub.core.engine import EngineLane
from hub.core.jobs import JobBook
from hub.core.supervisor import Spawn
from hub.core.vram import Vram
from hub.settings import DEFAULTS
from hub.worker import engineapi, enginewire
from tests.fakes.fake_probes import FakeProbes
from tests.fakes.mp4 import tiny_mp4

MODEL = "minimax_h3_ref2va"


def clip(seed: int = 7) -> dict:
    return enginewire.request_wire(engineapi.ClipRequest(MODEL, "a shot", (960, 544), seed, 124, steps=2))


def voice(sample: str = "/chars/Character 7.wav") -> dict:
    return enginewire.request_wire(engineapi.VoiceRequest("", sample, 7))


class Sup:
    """The supervisor's surface the lane uses; a `run` answers as the worker does: progress, the file in the outbox,
    task_done (`fail`: the task numbers that fail, with the engine's line)."""

    def __init__(self, on_event: Any, outbox: Path) -> None:
        self.on_event, self.outbox = on_event, outbox
        self.state, self.pid, self.spawn = "ready", 4242, Spawn("python", (), {}, outbox / "pid", False)
        self.sent: list[dict] = []
        self.fail: dict[int, str] = {}
        self.voice: dict = {"on": True, "lacking": [], "line": ""}
        self.asked: list[str] = []
        self.names = itertools.count(1)

    async def send(self, msg: dict) -> None:
        if msg.get("op") == "query" and msg.get("what") == "voice":
            asyncio.get_running_loop().call_soon(self.on_event, {"ev": "reply", "id": msg["id"], "data": self.voice})
            self.asked.append("voice")
        if msg.get("op") != "run":
            return
        self.sent.append(msg["request"])
        k, job = int(msg["task"]), msg["job"]
        base = {"job": job, "task": k}
        events = [{**base, "ev": "progress", "phase": "inference", "step": 1, "steps": 2, "pct": 50.0, "text": "x"},
                  {**base, "ev": "progress", "phase": "inference", "step": 2, "steps": 2, "pct": 100.0, "text": "x"}]
        if k in self.fail:
            events.append({**base, "ev": "task_done", "ok": False, "seconds": 1.0, "model": None,
                           "error": {"stage": "generation", "text": self.fail[k]}})
        else:
            path = self.outbox / f"made-{next(self.names)}.mp4"
            path.write_bytes(tiny_mp4(audio=True))
            events += [{**base, "ev": "output", "file": str(path)},
                       {**base, "ev": "task_done", "ok": True, "seconds": 1.0, "model": MODEL, "peak_vram_mb": None,
                        "peak_rss_mb": None}]
        loop = asyncio.get_running_loop()
        for ev in events:
            loop.call_soon(self.on_event, ev)

    async def start(self) -> None:
        self.state = "ready"

    async def stop(self) -> None:
        self.pid = None

    def reset(self) -> None:
        pass


class Bus:
    def __init__(self) -> None:
        self.seen: list[tuple[str, str, dict]] = []

    def publish(self, lane: str, type: str, data: dict, key: str | None = None, replace: bool = False) -> None:
        self.seen.append((lane, type, copy.deepcopy(data)))


class Files:
    """The dispatcher's view of the media roots: a clip by its id under `clips`."""

    def __init__(self, clips: Path) -> None:
        self.clips, self.deleted = clips, []

    def kind(self, item: str) -> str | None:
        return "clip" if item.startswith("clips/") and item.endswith(".mp4") else None

    def url(self, item: str) -> str:
        return f"/media/{item}"

    def thumb_url(self, item: str) -> str | None:
        return None

    def delete(self, ids: list[str]) -> list[str]:
        for item in ids:
            (self.clips / item.split("/", 1)[1]).unlink()
        self.deleted += ids
        return list(ids)


async def run(tmp_path: Path, monkeypatch: Any, plan: api.JobPlan, fail: dict[int, str] | None = None,
              voice_line: str = ""):
    monkeypatch.setattr(jobs, "PUBLISH_GAP_S", 0.0)
    data, state = tmp_path / "data", tmp_path / "data" / "engine" / "gpu0"
    (state / "outbox").mkdir(parents=True)
    lane = EngineLane("image.gpu0", None, Spawn("python", (), {}, tmp_path / "pid", False), data, state, "k")
    lane.sup = Sup(lane._on_event, state / "outbox")  # type: ignore[assignment]
    lane.sup.fail = fail or {}
    lane.sup.voice["line"] = voice_line
    emitted: list[tuple[str, dict]] = []
    lane_run = lane.run

    async def recorded(job: api.Job, emit: Any) -> None:
        await lane_run(job, lambda ev, d: (emitted.append((ev, copy.deepcopy(d))), emit(ev, d)))
    lane.run = recorded  # type: ignore[method-assign]
    bus, files = Bus(), Files(data / "clips")
    core_events: list[tuple[str, dict]] = []
    settings = copy.deepcopy(DEFAULTS)
    book = JobBook(bus, lambda: settings, lambda ev, d: core_events.append((ev, copy.deepcopy(d))))
    book.kinds["gen.image"] = lambda params: plan
    gpu = Vram(FakeProbes(), lambda: settings, bus)
    disp = Dispatcher(book, gpu, bus, files)
    ticks = itertools.count()
    disp.clock = lambda: float(next(ticks))
    disp.add_lane(lane)
    job = book.submit("gen.image", {})
    for _ in range(200):
        if job.state in ("done", "failed", "cancelled"):
            break
        await asyncio.sleep(0.01)
    return job, lane, emitted, bus, files, core_events


def normal(value: Any) -> Any:
    """The record with what changes from run to run (times, the file names the clock gives) put to fixed words."""
    text = json.dumps(value, sort_keys=True)
    names: dict[str, str] = {}
    for found in re.findall(r"clips/[0-9A-Za-z/_. -]+\.mp4", text):
        names.setdefault(found, f"clips/ITEM{len(names) + 1}.mp4")
    for old, new in names.items():
        text = text.replace(old, new)
    text = re.sub(r'"(created|started)": [0-9.e+]+', r'"\1": 0', text)
    text = re.sub(r'"j_[0-9a-f]{10}"', '"JOB"', text)
    return json.loads(text)


def record(emitted: list, bus: Bus, core_events: list) -> dict:
    return normal({"lane": emitted, "bus": [[lane, t, d] for lane, t, d in bus.seen if lane in ("jobs", "media")],
                   "core": core_events})


# The record of a plan of two clips with no inputs: the lane's events, the jobs and media bus messages, the core's
# job events.
GOLDEN = json.loads((Path(__file__).parents[1] / "fixtures" / "engine-graph-golden.json").read_text(encoding="utf-8"))


async def test_a_job_without_inputs_reports_as_before(tmp_path, monkeypatch):
    plan = api.JobPlan("image", MODEL, (clip(1), clip(2)), {"model": "H3", "kind": "clip"})
    job, _, emitted, bus, _, core = await run(tmp_path, monkeypatch, plan)
    assert job.state == "done"
    assert record(emitted, bus, core) == GOLDEN


def graph() -> api.JobPlan:
    return api.JobPlan("image", MODEL, (clip(), voice()),
                       {"model": "H3", "kind": "clip", "step_names": ["Render", "Voice"]},
                       inputs=({}, {"clip": (1, "file")}))


async def test_step_two_gets_step_ones_file_which_is_erased_when_done(tmp_path, monkeypatch):
    job, lane, emitted, bus, files, core = await run(tmp_path, monkeypatch, graph())
    assert job.state == "done", job.error
    first, second = [d for e, d in emitted if e == "output"]
    assert first["between"] is True and "between" not in second
    sent = lane.sup.sent[1]
    assert sent["kind"] == "voice" and sent["sample"] == "/chars/Character 7.wav"
    assert sent["clip"] == str(tmp_path / "data" / "clips" / first["item"].split("/", 1)[1])
    assert job.outputs == [second["item"]], "the render is not the job's"
    media = [d["item"]["id"] for lane_, t, d in bus.seen if lane_ == "media"]
    assert media == [second["item"]], "Media never saw the render"
    assert all(first["item"] not in r["outputs"] for lane_, t, r in bus.seen if lane_ == "jobs")
    assert files.deleted == [first["item"]] and not Path(sent["clip"]).exists()
    assert (tmp_path / "data" / "clips" / second["item"].split("/", 1)[1]).is_file()
    assert core[-1][1]["outputs"] == [second["item"]]


async def test_a_failed_voice_step_keeps_the_render_as_the_jobs_clip(tmp_path, monkeypatch):
    job, _, emitted, bus, files, core = await run(tmp_path, monkeypatch, graph(),
                                                   fail={2: "SeedVC is disabled in Configuration > Extensions"})
    assert job.state == "failed"
    assert job.error == "Voice step: SeedVC is disabled in Configuration > Extensions"
    (first,) = [d for e, d in emitted if e == "output"]
    assert job.outputs == [first["item"]] and files.deleted == []
    assert [d["item"]["id"] for lane_, t, d in bus.seen if lane_ == "media"] == [first["item"]]
    assert core[-1][1]["outputs"] == [first["item"]] and core[-1][1]["state"] == "failed"


async def test_a_failed_first_step_is_named_as_today(tmp_path, monkeypatch):
    job, *_ = await run(tmp_path, monkeypatch, graph(), fail={1: "Out of memory"})
    assert job.state == "failed" and job.error == "Out of memory" and job.outputs == []


async def test_seedvc_off_refuses_the_job_before_the_render(tmp_path, monkeypatch):
    off = "Voice conversion is off in the engine's config (audio_processors.seedvc.mode)"
    job, lane, emitted, bus, files, _ = await run(tmp_path, monkeypatch, graph(), voice_line=off)
    assert job.state == "failed" and job.error == off
    assert lane.sup.sent == [] and job.outputs == [], "nothing rendered"


async def test_a_job_without_a_voice_step_asks_nothing(tmp_path, monkeypatch):
    plan = api.JobPlan("image", MODEL, (clip(),), {"model": "H3", "kind": "clip"})
    job, lane, *_ = await run(tmp_path, monkeypatch, plan)
    assert job.state == "done" and lane.sup.asked == []


# a scene's job. Each shot's file is "kept" (lands as it is made, never erased); the join is sent their
# real paths; a step that fails is named, the first included.
def scene() -> api.JobPlan:
    items = [engineapi.JoinItem("", 0, 124, 24.0, 960, 544, 124, True) for _ in range(2)]
    join = enginewire.request_wire(engineapi.JoinRequest(items, engineapi.Canvas(960, 544, 24.0), [], 18, "medium"))
    return api.JobPlan("image", MODEL, (clip(1), clip(2), voice(), join),
                       {"model": "H3", "kind": "clip", "mode": "scene", "shots": 2,
                        "step_names": ["Shot 1 · Character 7 · 6.2 s", "Shot 2 · Character 6 · 5.2 s",
                                       "Shot 2 · voice", "Cut"]},
                       inputs=({}, {}, {"clip": (2, "file")},
                               {"items.0.path": (1, "kept"), "items.1.path": (3, "kept")}))


async def test_a_scenes_shots_land_as_made_and_the_join_reads_them(tmp_path, monkeypatch):
    job, lane, emitted, bus, files, _ = await run(tmp_path, monkeypatch, scene())
    assert job.state == "done", job.error
    shot1, render2, shot2, cut = [d for e, d in emitted if e == "output"]
    assert "between" not in shot1 and render2["between"] is True and "between" not in shot2
    real = [str(tmp_path / "data" / "clips" / d["item"].split("/", 1)[1]) for d in (shot1, shot2)]
    assert [i["path"] for i in lane.sup.sent[3]["items"]] == real
    assert job.outputs == [shot1["item"], shot2["item"], cut["item"]], "the cut is the newest"
    assert files.deleted == [render2["item"]], "only shot 2's render, a between file, is erased"


async def test_a_scenes_first_step_failing_is_named(tmp_path, monkeypatch):
    job, *_ = await run(tmp_path, monkeypatch, scene(), fail={1: "Out of memory"})
    assert job.state == "failed" and job.error == "Shot 1 · Character 7 · 6.2 s step: Out of memory"


async def test_a_scenes_cut_failing_keeps_every_shot(tmp_path, monkeypatch):
    job, _, emitted, _, files, _ = await run(tmp_path, monkeypatch, scene(), fail={4: "The clips differ in length"})
    assert job.state == "failed" and job.error == "Cut step: The clips differ in length"
    assert len(job.outputs) == 3 and files.deleted == [], "both shots, and shot 2's render as for any failure"
