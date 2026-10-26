"""VRAM manager over the image lanes (`api.JobLane`, one per GPU on this server).

NVML is read only at decision points (a job's start and end, a new screen, a lane change, a refresh, boot); two within
1 s share one reading, but a residency move reads at once and again `settle_s` later. Only the lane's own processes are
looked up in it (the baseline its learned peaks are measured from); other programs' memory is never a reason to wait.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from hub.core.api import JobLane
from hub.core.bus import Bus
from hub.core.plan import Plan, Situation, decide


class Vram:
    def __init__(self, probes: Any, settings: Callable[[], dict], bus: Bus) -> None:
        self.probes, self.settings, self.bus = probes, settings, bus
        self.learned: dict[str, dict[str, list[int]]] = {}   # peak needs seen this run, in memory only
        self.lanes: dict[str, JobLane] = {}
        self.queued: Callable[[str], int] = lambda lane_id: 0
        self.on_change: list[Callable[[], None]] = []
        self.loading: dict[str, str] = {}
        self.releasing: set[str] = set()
        self.minute_s, self.share_s, self.settle_s = 60.0, 1.0, 2.0
        self._idle: dict[str, asyncio.TimerHandle] = {}
        self._settle: asyncio.TimerHandle | None = None
        self._resident: set[tuple[str | None, str, str]] = set()
        self._at, self._read_at = -1e9, 0.0
        self._gpus: list[dict] | None = None

    # ---------------------------------------------------------------- readings
    def read(self, max_age: float | None = None) -> list[dict] | None:
        """A decision-point reading. Calls within `max_age` (default 1 s) share one."""
        if time.monotonic() - self._at >= (self.share_s if max_age is None else max_age):
            self._gpus = self.probes.gpus()
            self._at, self._read_at = time.monotonic(), time.time()
        return self._gpus

    def _view(self, uuid: str | None) -> dict | None:
        return next((g for g in self._gpus or [] if g["uuid"] == uuid), None)

    @staticmethod
    def _usage(lane: JobLane, g: dict) -> int:
        return sum(g["procs"].get(p, 0) for p in lane.pids())

    def _model(self, lane: JobLane) -> str | None:
        return self.loading.get(lane.id) or next((r.model for r in lane.residency()), None)

    # ---------------------------------------------------------------- learned needs
    def need(self, kind: str, model: str, uuid: str | None) -> int | None:
        values = self.learned.get(kind, {}).get(f"{model}|{uuid}")
        return max(values) if values else None

    def learn(self, kind: str, model: str, uuid: str | None, mb: int) -> None:
        table = self.learned.setdefault(kind, {})
        key = f"{model}|{uuid}"
        table[key] = (table.get(key, []) + [int(mb)])[-3:]

    def baseline(self, lane: JobLane) -> int | None:
        """Memory used by everything except this lane, from a reading at the job's start."""
        self.read()
        g = self._view(lane.gpu_uuid)
        return None if g is None else max(0, g["used_mb"] - self._usage(lane, g))

    # ---------------------------------------------------------------- plan
    def plan(self, lane: JobLane, model: str, label: str) -> Plan:
        return decide(Situation(lane=lane.id, model=model, label=label,
                                resident=tuple(r.model for r in lane.residency()),
                                need=self.need("vram", model, lane.gpu_uuid)))

    # ---------------------------------------------------------------- lanes
    def register_lane(self, lane: JobLane) -> None:
        self.lanes[lane.id] = lane
        lane.on_change = self.changed  # the lane calls it when its residency changes
        self.changed()

    def changed(self) -> None:
        moved = self._moved()  # a reading from before it is stale, and memory settles after it
        self.read(max_age=0 if moved else None)
        self.publish()
        if moved:
            self.close()
            self._settle = asyncio.get_running_loop().call_later(self.settle_s, self._settled)
        for cb in self.on_change:
            cb()

    def _moved(self) -> bool:
        now = {(x.gpu_uuid, x.id, r.model) for x in self.lanes.values() for r in x.residency()}
        moved, self._resident = now ^ self._resident, now
        return any(g["uuid"] == uuid for g in self._gpus or [] for uuid, _, _ in moved)

    def _settled(self) -> None:
        self._settle, self._at = None, -1e9  # a fresh reading, not one shared with the event
        self.changed()

    def close(self) -> None:  # the hub stops: no reading after it
        if self._settle is not None:
            self._settle.cancel()

    def publish(self) -> None:
        self.bus.publish("gpu", "gpu", self.snapshot(), key="gpu")

    def snapshot(self) -> dict:
        uuids = [g["uuid"] for g in self._gpus or []]
        uuids += [u for u in dict.fromkeys(lane.gpu_uuid for lane in self.lanes.values()) if u not in uuids]
        return {"read_at": self._read_at or None, "gpus": [self._gpu(u) for u in uuids]}

    def _gpu(self, uuid: str | None) -> dict:
        g, lanes = self._view(uuid), [x for x in self.lanes.values() if x.gpu_uuid == uuid]
        return {"uuid": uuid, **{k: (g or {}).get(k) for k in ("name", "total_mb", "used_mb", "free_mb")},
                "lanes": [{"id": x.id, "kind": x.kind, "state": self.lane_state(x), "model": self._model(x)}
                          for x in lanes],
                "unknown": g is None}

    def lane_state(self, lane: JobLane) -> str:
        if lane.id in self.releasing:
            return "unloading"
        if self.loading.get(lane.id):
            return "loading"
        if lane.busy():
            return "busy"
        if not lane.ready():
            return "down"
        return "ready" if lane.residency() else "idle"

    def engines(self) -> dict:
        states = {"busy": "busy", "loading": "busy", "down": "down"}
        return {i: states.get(self.lane_state(self.lanes[i]), "ready") for i in sorted(self.lanes)}

    async def release(self, lane_ids: list[str] | tuple[str, ...], reason: str) -> bool:
        lanes = [self.lanes[i] for i in lane_ids if i in self.lanes]
        self.releasing.update(x.id for x in lanes)
        self.publish()
        try:
            results = await asyncio.gather(*(x.release(reason) for x in lanes), return_exceptions=True)
        finally:
            self.releasing.difference_update(x.id for x in lanes)
        self.changed()
        return all(r is True for r in results)

    # ---------------------------------------------------------------- idle unload (per image lane)
    def job_started(self, lane_id: str) -> None:
        self._cancel_idle(lane_id)

    def job_ended(self, lane_id: str) -> None:
        self.changed()
        self.arm_idle(lane_id)

    def arm_idle(self, lane_id: str) -> None:
        self._cancel_idle(lane_id)
        v, lane = self.settings()["vram"], self.lanes.get(lane_id)
        if not v["idle_unload"] or lane is None or lane.busy() or not lane.residency() or self.queued(lane_id):
            return
        delay = v["idle_minutes"] * self.minute_s
        loop = asyncio.get_running_loop()
        self._idle[lane_id] = loop.call_later(delay, lambda: loop.create_task(self._idle_fire(lane_id)))

    def rearm(self) -> None:
        for lane_id in self.lanes:
            self.arm_idle(lane_id)

    def _cancel_idle(self, lane_id: str) -> None:
        handle = self._idle.pop(lane_id, None)
        if handle is not None:
            handle.cancel()

    async def _idle_fire(self, lane_id: str) -> None:
        self._idle.pop(lane_id, None)
        lane = self.lanes.get(lane_id)
        if lane is not None and not lane.busy() and not self.queued(lane_id) and lane.residency():
            await self.release([lane_id], "idle")
