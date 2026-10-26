"""Jobs: five states, one FIFO per lane, memory only (lost on restart).

Every job, from a screen or the assistant, is queued at once.
The latest finished job per tool stays until dismissed or that tool's next job starts.
"""
from __future__ import annotations

import asyncio
import copy
import secrets
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from hub.core import jobgraph
from hub.core.api import Invalid, Job, JobLane, JobPlan
from hub.core.bus import Bus
from hub.core.messages import Refused

TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running", "cancelled", "failed"},      # failed before running: refused by the plan
    "running": {"running", "done", "failed", "cancelled"},
    "done": set(), "failed": set(), "cancelled": set(),
}
PUBLISH_GAP_S = 0.25


def move(job: Job, to: str) -> None:
    if to not in TRANSITIONS[job.state]:
        raise ValueError(f"Job {job.id} cannot go from {job.state} to {to}")
    job.state = to  # type: ignore[assignment]


@dataclass(eq=False)
class Entry:
    job: Job
    params: dict
    created: float = field(default_factory=time.time)
    started: float | None = None
    cancel_requested: bool = False
    phase: str | None = None
    step: int = 0
    steps: int = 0
    text: str | None = None
    acc_s: float = 0.0
    acc_steps: int = 0
    done_steps: int = 0
    last: tuple[float, int, int, str] | None = None
    baseline: int | None = None
    published: float = 0.0
    timer: asyncio.TimerHandle | None = None


class JobBook:
    def __init__(self, bus: Bus, settings: Callable[[], dict], emit: Callable[[str, dict], None]) -> None:
        self.bus, self.settings, self.emit = bus, settings, emit
        self.entries: dict[str, Entry] = {}
        self.queues: dict[str, deque[str]] = {}
        self.lanes: dict[str, JobLane] = {}
        self.kinds: dict[str, Callable[[dict], JobPlan]] = {}
        self.terminal: dict[str, str] = {}
        self.kick: Callable[[str], None] = lambda lane_id: None
        self.stop_running: Callable[[Entry], None] = lambda e: None
        self.session_open: Callable[[], bool] = lambda: True     # set by the core: a window is connected

    # ---------------------------------------------------------------- submit
    def submit(self, kind: str, params: dict, by: str = "screen") -> Job:
        """Queue a job. `by` is who pressed: the module id whose `ctx.jobs.submit` made it, or "screen" (a web
        press); `job.submitted` carries it."""
        build = self.kinds.get(kind)
        if build is None:
            raise Refused("not_found", "Unknown job kind")
        if not isinstance(params, dict):
            raise Invalid("params", "params must be an object")
        plan = build(copy.deepcopy(params))
        if not isinstance(plan, JobPlan) or not (plan.tasks or plan.prepare):
            raise Invalid("params", "Nothing to run")
        if plan.prepare is None:                     # a job that plans itself is checked when it has
            jobgraph.check(plan)                     # a step that reads an earlier one's file
        if not any(lane.kind == plan.lane_kind for lane in self.lanes.values()):
            raise Refused("unavailable", "Engine is offline")
        lanes = [lane for lane in self.lanes.values() if lane.kind == plan.lane_kind]
        hot = [lane for lane in lanes if any(r.model == plan.model for r in lane.residency())]
        lane = hot[0] if hot else min(lanes, key=lambda x: len(self.queues[x.id]))
        if len(self.queues[lane.id]) >= self.settings()["queue"]["max_waiting"]:
            raise Refused("queue_full", "Queue is full")
        job = Job(id="j_" + secrets.token_hex(5), kind=kind, tool=kind.split(".", 1)[0], state="queued", plan=plan,
                  lane=lane.id)
        e = Entry(job, copy.deepcopy(params))
        self.entries[e.job.id] = e
        self.queues[lane.id].append(e.job.id)
        self.publish(e)
        self.emit("job.submitted", {"job": e.job.id, "kind": e.job.kind, "tool": e.job.tool, "by": by,
                                    "params": copy.deepcopy(e.params)})
        self.kick(lane.id)
        return job

    # ---------------------------------------------------------------- api.Jobs
    def get(self, job_id: str) -> Job | None:
        e = self.entries.get(job_id)
        return e.job if e else None

    def cancel(self, job_id: str) -> Job | None:
        e = self.entries.get(job_id)
        if e is None:
            return None
        state = e.job.state
        if state == "queued":
            lane = e.job.lane or ""
            if job_id in self.queues.get(lane, ()):
                self.queues[lane].remove(job_id)
            move(e.job, "cancelled")
            self.emit("job.finished", {"job": e.job.id, "kind": e.job.kind, "tool": e.job.tool,
                                       "state": "cancelled", "outputs": [], "notes": dict(e.job.notes)})
            self._forget(e)
            self.positions(lane)
            self.kick(lane)
        elif state == "running" and not e.cancel_requested:
            e.cancel_requested = True
            self.publish(e)
            self.stop_running(e)
        return e.job

    def card(self, job_id: str) -> dict | None:
        """The job's card as the `jobs` lane shows it (`record`); None when the job is gone."""
        e = self.entries.get(job_id)
        return self.record(e) if e else None

    def note(self, job_id: str, **values: Any) -> Job | None:
        """Merge `values` into the job's `notes` (what the Hub learned after submit: the plan, the judges' verdicts)
        and publish its card. None when the job is gone."""
        e = self.entries.get(job_id)
        if e is None:
            return None
        e.job.notes.update(values)
        self.publish(e)
        return e.job

    def refuse(self, job_id: str, text: str) -> Job | None:
        """A queued job fails now with that one line (a plan the engine would not make); a job that is
        running or over is left as it is. None when the job is gone."""
        e = self.entries.get(job_id)
        if e is None:
            return None
        if e.job.state == "queued":
            lane = e.job.lane or ""
            if job_id in self.queues.get(lane, ()):
                self.queues[lane].remove(job_id)
            e.job.error = text
            self.finish(e, "failed")
            self.positions(lane)
            self.kick(lane)
        return e.job

    def clear(self, lane_id: str | None = None) -> int:
        ids = [j for lane, q in self.queues.items() if lane_id in (None, lane) for j in q]
        for job_id in ids:
            self.cancel(job_id)
        return len(ids)

    def dismiss(self, job_id: str) -> None:
        e = self.entries.get(job_id) if isinstance(job_id, str) else None
        if e is None:
            raise Refused("not_found", "That job is gone")
        if e.job.state not in ("done", "failed", "cancelled"):
            raise Refused("forbidden", "Only a finished job can be dismissed")
        self._forget(e)

    # ---------------------------------------------------------------- lifecycle hooks (dispatcher)
    def started(self, e: Entry) -> None:
        old = self.terminal.pop(e.job.tool, None)
        if old in self.entries:
            self._forget(self.entries[old])
        self.publish(e)
        self.positions(e.job.lane or "")

    def finish(self, e: Entry, state: str) -> None:
        move(e.job, state)
        old = self.terminal.get(e.job.tool)
        if old is not None and old != e.job.id and old in self.entries:
            self._forget(self.entries[old])
        self.terminal[e.job.tool] = e.job.id
        self.publish(e)
        self.emit("job.finished", {"job": e.job.id, "kind": e.job.kind, "tool": e.job.tool, "state": state,
                                   "outputs": list(e.job.outputs), "notes": dict(e.job.notes)})
        if not self.session_open():
            self._forget(e)                  # nobody is there to see it, so it is not kept for anyone

    def forget_finished(self) -> None:
        """The session ended: finished jobs go; queued and running ones stay, and go as soon as they finish."""
        for e in [e for e in self.entries.values() if e.job.state in ("done", "failed", "cancelled")]:
            self._forget(e)

    def _forget(self, e: Entry) -> None:
        self.entries.pop(e.job.id, None)
        if e.timer is not None:
            e.timer.cancel()
        if self.terminal.get(e.job.tool) == e.job.id:
            del self.terminal[e.job.tool]
        self.bus.publish("jobs", "job.gone", {"id": e.job.id}, key=f"job:{e.job.id}", replace=False)

    # ---------------------------------------------------------------- views
    def record(self, e: Entry) -> dict:
        j, plan = e.job, e.job.plan
        q = self.queues.get(j.lane or "", deque())
        n = len(plan.tasks)
        noun = "image" if n == 1 else "images"
        title = plan.summary.get("title") or f"{n} {noun} · {plan.summary.get('model') or plan.model}"
        progress = None
        if j.state == "running":
            progress = {"phase": e.phase, "index": j.task, "count": n, "step": e.step, "steps": e.steps,
                        "pct": j.pct, "eta_s": j.eta_s, "text": e.text}
        return {"id": j.id, "tool": j.tool, "kind": j.kind, "title": title, "lane": j.lane, "state": j.state,
                "created": e.created, "started": e.started,
                "position": list(q).index(j.id) + 1 if j.state == "queued" and j.id in q else None,
                "cancel_requested": e.cancel_requested,
                "progress": progress, "outputs": list(j.outputs), "error": {"text": j.error} if j.error else None,
                "summary": plan.summary, "notes": j.notes}

    def snapshot(self) -> list[dict]:
        return [self.record(e) for e in sorted(self.entries.values(), key=lambda x: x.created)]

    def positions(self, lane_id: str) -> None:
        for job_id in self.queues.get(lane_id, ()):
            self.publish(self.entries[job_id])

    def publish(self, e: Entry, progress_only: bool = False) -> None:
        """State changes go out at once; progress at most 4 times a second per job (latest wins)."""
        now = time.monotonic()
        if progress_only and now - e.published < PUBLISH_GAP_S:
            if e.timer is None:
                e.timer = asyncio.get_running_loop().call_later(PUBLISH_GAP_S - (now - e.published), self._flush, e)
            return
        if e.timer is not None:
            e.timer.cancel()
            e.timer = None
        e.published = now
        self.bus.publish("jobs", "job", self.record(e), key=f"job:{e.job.id}", replace=progress_only)

    def _flush(self, e: Entry) -> None:
        e.timer = None
        if self.entries.get(e.job.id) is e:
            self.publish(e, progress_only=True)
