"""The engine lane's memory between jobs: which model the worker holds, and when the worker is stopped to free it.

Stopping the worker is the release "Clear the GPU cache" sends (`gpu.release` -> `Vram.release` -> `release()`): the
process exits and the CUDA context, the allocator's cache and pinned memory go with it. The engine's own swap inside
one process frees less, so the lane releases:
  - before a job whose model differs from the one the worker holds (`_resident`, the last task's model); the same
    model is never released;
  - after a job on a video-kind model, whether it made its clip or failed;
  - when the job's model wants a memory profile the worker was not started with (`supervisor.job_profile`);
  - after a job that loads no model (`api.NO_MODEL`, a join) when that job started the worker and it holds no model
    (as a catalog query's start is undone, `enginequery._load`): the idle unload arms only for a resident model.
Before any of that, every task of a job is checked as the worker will parse it (`checked`).

A mixin of `engine.EngineLane`, which holds the state named below.
"""
from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Callable
from pathlib import Path
from typing import Any

from hub.core import api, jobgraph
from hub.core.supervisor import EngineFailed, Supervisor, job_profile, worker_args
from hub.worker.enginewire import request_parse

NOT_A_REQUEST = "Task {} is not a request the engine takes: {}"


def checked(job: api.Job) -> None:
    """Every task of the job is a request the worker will parse (`enginewire.request_parse`: its kind, its fields,
    its pictures' roles), checked before the worker is started or sent anything; else one line. A join's item is
    sent with an empty `path` only where the job's inputs fill it (`jobgraph.named`, its sounds too)."""
    for k, request in enumerate(job.plan.tasks, 1):
        try:
            parsed = request_parse(request)
            for key in ("items", "audio"):
                filled = jobgraph.named(job.plan.inputs[k - 1], key) if job.plan.inputs else set()
                for i, item in enumerate(getattr(parsed, key, None) or ()):
                    if item.path == "" and i not in filled:
                        raise ValueError(f"request.{key}[{i}].path: empty")
        except ValueError as exc:
            raise EngineFailed("runtime", NOT_A_REQUEST.format(k, exc)) from None


class LaneMemory:
    sup: Supervisor
    engine: dict[str, Any] | None
    state: Path
    _catalog: dict[str, Any] | None
    _model: str | None
    _resident: str | None              # the model of the last task sent to the running worker; None: none or stopped
    _started: bool                     # this `NO_MODEL` job found the worker not ready (so its run starts it)

    def cached_catalog(self) -> dict[str, Any] | None:
        raise NotImplementedError

    def _set_model(self, model: Any) -> None:
        raise NotImplementedError

    def held(self) -> str | None:
        """The model the running worker holds: its last task's, else the one it reported."""
        return (self._resident or self._model) if self.sup.pid is not None else None

    async def _kind(self, job: api.Job) -> str | None:
        """The catalog kind of the job's model; a catalog not read yet: "video" when its tasks are clip requests."""
        cat = self._catalog or await asyncio.to_thread(self.cached_catalog)
        kind = next((m.get("kind") for m in (cat or {}).get("models", []) if m.get("id") == job.plan.model), None)
        if kind is None and job.plan.tasks and all(t.get("kind") == "video" for t in job.plan.tasks):
            return "video"
        return kind

    async def _unload(self, emit: Callable[[str, dict], None] | None = None) -> None:
        """Stop the worker and wait for it to exit (callers hold the lane)."""
        held = self.held()
        await self.sup.stop()
        self._resident = None
        self._set_model(None)
        if emit is not None and held:
            emit("model", {"state": "released", "model": held})

    async def _before(self, job: api.Job, kind: str | None, emit: Callable[[str, dict], None]) -> None:
        """Before a job (the lane held): the worker's profile for this model's kind, and no other model in it. A job
        that loads no model (`api.NO_MODEL`, a join) keeps the worker and whatever it holds."""
        if job.plan.model == api.NO_MODEL:
            self._started = self.sup.state != "ready"
            return
        await self._follow_profile(kind)
        held = self.held()
        if held is not None and held != job.plan.model:
            await self._unload(emit)

    async def _after(self, job: api.Job, kind: str | None, emit: Callable[[str, dict], None]) -> None:
        """After a job on a video model, made or failed: its memory is given back at once. After a job that loads
        no model and started the worker: that worker is stopped unless it holds a model."""
        started, self._started = self._started, False
        if job.plan.model == api.NO_MODEL:
            if started and self.held() is None and (self.sup.pid is not None or self.sup.state == "starting"):
                await self._unload(emit)
            return
        if kind == "video" and (self.sup.pid is not None or self.sup.state == "starting"):
            await self._unload(emit)

    async def _follow_profile(self, kind: str | None) -> None:
        """The worker's arguments for the profile this kind wants; a running worker started with others is stopped,
        so `_ensure` starts it again with these."""
        if self.engine is None:
            return
        args = worker_args(self.engine, self.state, job_profile(self.engine, kind))
        if args == self.sup.spawn.args:
            return
        self.sup.spawn = dataclasses.replace(self.sup.spawn, args=args)
        if self.sup.pid is not None or self.sup.state == "starting":
            await self._unload()
