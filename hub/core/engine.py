"""The image engine lane: one local worker per GPU. Implements `api.JobLane` and `api.Engine`.

`run(job, emit)` runs the job's N tasks in order, each given what earlier ones made (`jobgraph.fill`), and reports
through `emit(event, data)`:
  task       {task, of}                                   image k of N starts
  model      {state: loading|loaded, model}               residency changed
  progress   {task, of, phase, step, steps, pct, text}    pct covers the whole job
  output     {task, item, kind, w, h}                     a picture landed in <data>/outputs, a clip in <data>/clips
                                                          (+ between: true when a later step reads it)
  task_done  {task, seconds, model, peak_vram_mb, peak_rss_mb}   the peaks feed the per-model need (dispatch)
  skip       {task, of}                                   a take not needed: its task is not sent
  model      {state: released, model}                     the lane stopped the worker to free that model
It returns when every image is made; otherwise it raises `EngineFailed` (stage, one-line text),
also after `cancel()` (stage "cancelled"). The worker starts on demand; `release()` stops it, and so does the lane
itself around jobs (another model next, a video model done, another memory profile): see `enginelane`. The catalog
side (`query`) is `enginequery`.
"""
from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import itertools
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from hub.core import api, autoreg, enginecat, jobgraph
from hub.core.enginecat import catalog_key
from hub.core.enginelane import LaneMemory, checked
from hub.core.enginequery import CatalogQueries
from hub.core.files import CLIPS, SOUNDS
from hub.core.supervisor import EngineFailed, Spawn, Supervisor, make_spawn, worker_args

OUTPUTS = "outputs"                       # <data>/outputs is the media root "out"


class EngineLane(CatalogQueries, LaneMemory):
    kind: api.LaneKind = "image"

    def __init__(self, lane_id: str, gpu_uuid: str | None, spawn: Spawn, data_dir: Path, state: Path,
                 catalog_key: str) -> None:
        self.id, self.gpu_uuid = lane_id, gpu_uuid
        self.sup = Supervisor(spawn, self._on_event)
        self.on_change: Callable[[], None] = lambda: None   # set by the VRAM manager
        self.outputs, self.clips, self.sounds = data_dir / OUTPUTS, data_dir / CLIPS, data_dir / SOUNDS
        self.outbox = state / "outbox"                      # the worker's outbox: <state>/outbox
        self.cache = data_dir / "engine" / "catalog.json"
        self.catalog_key, self.state = catalog_key, state
        self.engine: dict[str, Any] | None = None           # set: the key follows the folders on each query
        self.lora_roots: list[str] = []                      # the LoRA folders in Settings (family subfolders)
        self._restart = False
        self._catalog: dict[str, Any] | None = None
        self._found: autoreg.Found | None = None    # the last registry pass: one record per weight file
        self._files: tuple[str, dict[str, Any]] | None = None   # (catalog key, each model's file parts)
        self._model: str | None = None
        self._resident: str | None = None
        self._started = False                               # a NO_MODEL job started the worker: see enginelane
        self._job: str | None = None
        self._cancelling = False
        self._cancelled: set[str] = set()                    # cancels that came before their run took the lane
        self._events: asyncio.Queue[dict[str, Any]] | None = None
        self._queries: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._ids = itertools.count(1)
        self._lock = asyncio.Lock()
        self._fetching, self._fetches, self._fresh = asyncio.Lock(), 0, 0   # one fetch at a time: see _load
        self._bg: set[asyncio.Task[None]] = set()

    # ---------------------------------------------------------------- api.JobLane
    def residency(self) -> list[api.Resident]:
        return [api.Resident(self._model)] if self._model else []

    def busy(self) -> bool:
        return self._job is not None

    def pids(self) -> list[int]:
        return [self.sup.pid] if self.sup.pid else []

    def ready(self) -> bool:
        return self.sup.state != "down"

    async def release(self, reason: str) -> bool:
        """Stop the worker (frees VRAM, RAM and the CUDA context). Refused while a job runs."""
        if self._lock.locked():
            return False
        async with self._lock:
            await self._unload()
        return True

    def reset(self) -> None:
        """Start pressed: clear `down` so the next job may start the worker."""
        self.sup.reset()

    async def stop(self) -> None:
        await self._unload()

    # ---------------------------------------------------------------- jobs
    async def cancel(self, job_id: str) -> None:
        if self._job != job_id:
            self._cancelled.add(job_id)
            return
        self._cancelling = True
        with contextlib.suppress(EngineFailed):
            await self.sup.send({"op": "cancel", "job": job_id})

    async def run(self, job: api.Job, emit: Callable[[str, dict], None]) -> None:
        async with self._lock:
            self._job, self._cancelling = job.id, job.id in self._cancelled
            self._cancelled.discard(job.id)
            kind = None
            try:
                checked(job)                       # every request as the worker parses it, before it starts
                kind = await self._kind(job)
                if not self._cancelling:
                    await self._before(job, kind, emit)
                    await self._ensure()
                plan = job.plan
                tasks, made, between = plan.tasks, {}, jobgraph.between(plan)
                if not self._cancelling and any(t.get("kind") == "voice" for t in tasks):   # asked
                    line = ((await self._ask("voice")) or {}).get("line")                   # before the render
                    if line:
                        raise EngineFailed("runtime", str(line))
                for k, request in enumerate(tasks, 1):
                    if self._cancelling:
                        raise EngineFailed("cancelled", "Cancelled")
                    if plan.takes and not jobgraph.runs(plan, k, job.takes, made, plan.judge):
                        emit("skip", {"task": k, "of": len(tasks)})
                        continue
                    emit("task", {"task": k, "of": len(tasks)})
                    sent = jobgraph.fill(request, plan.inputs[k - 1] if plan.inputs else {}, made, k, plan, job.takes)
                    try:
                        made[k] = await self._task(job.id, k, len(tasks), sent, emit, plan.model, k in between)
                    except EngineFailed as ex:            # a take that fails is a bad take
                        if not (plan.takes and ex.stage in ("generation", "runtime") and not self._cancelling
                                and self.sup.state == "ready" and jobgraph.absorbs(plan, k, made, plan.judge)):
                            raise
                        take = (jobgraph.where(plan, k) or (0, 0, 0))[1]
                        job.takes[k] = api.Take(False, (), jobgraph.FAILED.format(take, ex.text))
                        job.notes.setdefault("takes", {})[str(k)] = {"passes": False, "line": job.takes[k].line}
            finally:
                self._job, self._events = None, None
                if self._restart:
                    self._restart = False
                    await self._unload()
                else:
                    await self._after(job, kind, emit)
                self.on_change()

    async def configure(self, engine: Mapping[str, Any], lora_roots: list[str], restart: bool) -> None:
        """New settings. Engine paths or model folders: stop the worker (after a running job), drop the catalog."""
        self.lora_roots, self.engine = list(lora_roots), dict(engine)    # the video profile: read at the next job
        if not restart:
            return
        env = {k: v for k, v in self.sup.spawn.env.items() if k not in ("CC", "CXX")}
        env |= {var: str(engine[key]) for key, var in (("cc", "CC"), ("cxx", "CXX")) if engine.get(key)}
        self.sup.spawn = dataclasses.replace(self.sup.spawn, python=str(engine.get("python") or ""),
                                             args=worker_args(engine, self.state), env=env)
        self.catalog_key, self._catalog = catalog_key(self.engine), None
        self.sup.reset()
        if self._lock.locked():
            self._restart = True
            return
        async with self._lock:
            await self._unload()

    async def _ensure(self) -> None:
        if self.sup.state != "ready":
            await self.sup.start()
            task = asyncio.create_task(self._refetch())
            self._bg.add(task)
            task.add_done_callback(self._bg.discard)

    async def _refetch(self) -> None:
        async with self._fetching:            # a worker a job started reads the catalog again, after any fetch
            await self._fetch_catalog()

    async def _task(self, job_id: str, k: int, n: int, request: dict, emit: Callable[[str, dict], None],
                    model: str, between: bool = False) -> str | None:
        """One task to its end; -> the real path of the file it landed (None: none). `between`: its file is for a
        later step, its `output` event says so."""
        self._events, frac, made = asyncio.Queue(), 0.0, None
        await self.sup.send({"op": "run", "job": job_id, "task": k, "request": request})
        model = str(request.get("model") or model)   # a request naming its own model loads that one
        if model != api.NO_MODEL:
            self._resident = model              # the worker loads it now (it frees another first, not always enough)
        while True:
            msg = await self._events.get()
            ev = msg["ev"]
            if ev == "model":
                emit("model", {"state": msg.get("state"), "model": msg.get("model")})
            elif ev == "progress":
                frac, data = enginecat.progress(msg, k, n, frac)
                emit("progress", data)
            elif ev == "output":
                landed = await asyncio.to_thread(enginecat.land, str(msg.get("file")), self.outbox, self.outputs,
                                                 self.clips, self.sounds)
                item = landed.pop("id")
                head, rest = item.split("/", 1)
                made = str({CLIPS: self.clips, SOUNDS: self.sounds, enginecat.OUTPUT_ID: self.outputs}[head] / rest)
                emit("output", {"task": k, "item": item, **landed,              # + kind, w, h (or seconds)
                                **({"between": True} if between else {})})
            elif ev == "exit":
                stage = "cancelled" if self._cancelling else "crashed" if msg.get("crash") else "runtime"
                raise EngineFailed(stage, str(msg.get("text") or "The engine stopped"))
            elif ev == "task_done":
                emit("task_done", {"task": k, **{key: msg.get(key) for key in
                                                 ("seconds", "model", "peak_vram_mb", "peak_rss_mb")},
                                   **({"judge": msg["judge"]} if isinstance(msg.get("judge"), dict) else {})})
                await asyncio.to_thread(enginecat.sweep, self.outbox)     # nothing of a task stays behind
                if not msg.get("ok"):
                    error = msg.get("error") or {}
                    raise EngineFailed(str(error.get("stage") or "generation"), str(error.get("text") or "Failed"))
                return made

    # ---------------------------------------------------------------- worker events
    def _on_event(self, msg: dict[str, Any]) -> None:
        ev = msg.get("ev")
        if ev == "reply":
            if (fut := self._queries.pop(str(msg.get("id")), None)) is not None and not fut.done():
                fut.set_result(msg)
            return
        if ev == "model":
            self._set_model(msg.get("model"))
        if ev == "exit":
            self._resident = None
            self._set_model(None)
            for fut in self._queries.values():
                if not fut.done():
                    fut.set_exception(EngineFailed("crashed", str(msg.get("text"))))
            self._queries.clear()
        if ev == "task_done" and msg.get("job") == self._job:
            self._set_model(msg.get("model"))
        if self._events is not None and (ev == "exit" or msg.get("job") in (None, self._job)):
            self._events.put_nowait(msg)

    def _set_model(self, model: Any) -> None:
        model = str(model) if model else None
        if model != self._model:
            self._model = model
            self.on_change()


def create(settings: Mapping[str, Any], data_dir: Path, probes: Any) -> tuple[api.JobLane, api.Engine]:
    """One image lane for the first GPU in `settings["gpus"]` marked `engine` (else GPU 0); several: call per GPU."""
    engine = settings["engine"]
    gpu = next((g for g in settings.get("gpus", []) if g.get("engine")), {"id": "gpu0", "index": 0, "uuid": None})
    uuid = gpu.get("uuid")
    if not uuid:
        with contextlib.suppress(Exception):
            uuid = next((g["uuid"] for g in probes.gpus() or [] if g["index"] == gpu.get("index", 0)), None)
    state = data_dir / "engine" / gpu["id"]
    (state / "config" / "wgp_config.json.tmp").unlink(missing_ok=True)  # a worker killed while seeding it
    spawn = make_spawn(engine, data_dir, state, gpu["id"], uuid or str(gpu.get("index", 0)),
                       bool(settings.get("diagnostics")))
    lane = EngineLane(f"image.{gpu['id']}", uuid, spawn, data_dir, state, catalog_key(engine))
    lane.engine = dict(engine)
    lane.lora_roots = list(settings.get("modules", {}).get("loras", {}).get("folders", []))
    if not os.path.isfile(spawn.python) or not os.path.isdir(str(engine.get("root") or "")):
        lane.sup.state, lane.sup.down_text = "down", "The engine's Python or folder is not set up; run hub init"
    return lane, lane
