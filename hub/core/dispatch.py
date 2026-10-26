"""The dispatcher: event-driven, one pump per lane, no polling. Head-of-line blocking is deliberate (no reordering).

It runs when a job is queued or ends, or a lane changes (Start included). The head job runs at once, or, when the
lane holds a different model, after that is released; an offline or busy lane is kicked again by its own change.
Lane events (`JobLane.run(job, emit)`, as `core/engine.py` sends them):
  task      {task, of}                         image k of N starts
  model     {state: loading|loaded|released, model}
  progress  {task, phase, step?, steps?, pct?, text?}   pct covers the whole job
  output    {task, item, w?, h?, between?}      between: a later step reads it; held until the job ends
  task_done {task, seconds?, peak_vram_mb?, ok?, error?}   a take's: asked of the plan's judge
  skip      {task, of}                         a take not needed: the card moves on
  error     {text, fatal?}
`run` returns when the job is over; raising marks it failed (or cancelled after a cancel).
A plan with `prepare` has its first step here, before `run`: `prepare(say)` builds the rest of the job,
each `say` line shown as progress `{phase: "planning", text}`; a cancel stops it and nothing is rendered.
A plan with `finish` has its last step here, after `run` whatever its end: `finish(landed)`, given the
media id each task landed in Media (task -> id); it submits nothing. Its raise fails a done job, `Sequence: …`.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any

from hub.core import jobgraph
from hub.core.api import NO_MODEL, Invalid, JobLane, JobPlan
from hub.core.bus import Bus
from hub.core.files import Files
from hub.core.jobs import Entry, JobBook, move
from hub.core.vram import Vram


def one_line(value: Any) -> str:
    text = value.get("text", "") if isinstance(value, dict) else str(value or "")
    first = text.strip().splitlines()[0] if text.strip() else ""
    return (first or "Engine error")[:200]


def step_line(e: Entry, text: str) -> str:
    """A failure in a step after the first of a job of steps names the step: `Voice step: <line>`; a
    scene's names every step, the first included: `Shot 1 · Character 1 · 6.2 s step: <line>`."""
    steps, k = e.job.plan.summary.get("step_names"), e.job.task
    first = 1 if e.job.plan.summary.get("mode") == "scene" else 2
    if not (e.job.plan.inputs or first == 1) or not isinstance(steps, list) or not first <= k <= len(steps):
        return text
    return one_line(f"{steps[k - 1]} step: {text}")


def checked(was: JobPlan, plan: object) -> JobPlan:
    """A plan `prepare` returned, held to what `submit` asks of one, on the lane and model the job was queued for."""
    if not isinstance(plan, JobPlan) or not plan.tasks or plan.prepare is not None:
        raise Invalid("params", "Planning gave nothing to run")
    if (plan.lane_kind, plan.model) != (was.lane_kind, was.model):
        raise Invalid("params", "Planning gave a job for another model")
    jobgraph.check(plan)
    return plan


class Dispatcher:
    def __init__(self, book: JobBook, gpu: Vram, bus: Bus, files: Files) -> None:
        self.book, self.gpu, self.bus, self.files = book, gpu, bus, files
        self.running: dict[str, str] = {}
        self.clock = time.monotonic
        self._pumping: set[str] = set()
        self._again: set[str] = set()
        self._tasks: set[asyncio.Task] = set()
        self._held: dict[str, list[tuple[str, dict]]] = {}   # job -> its between files and their events
        self._planning: dict[str, asyncio.Task] = {}         # job -> its `prepare` while it runs
        self._kept: dict[str, dict[int, str]] = {}           # job -> task -> the id it landed in Media
        book.kick, book.stop_running = self.kick, self.stop
        gpu.queued = lambda lane_id: len(book.queues.get(lane_id, ()))
        gpu.on_change.append(self.kick_all)

    def add_lane(self, lane: JobLane) -> None:
        self.book.lanes[lane.id] = lane
        self.book.queues.setdefault(lane.id, deque())
        self.gpu.register_lane(lane)

    def _spawn(self, coro: Any) -> None:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # ---------------------------------------------------------------- pump
    def kick(self, lane_id: str) -> None:
        if lane_id not in self.book.lanes:
            return
        if lane_id in self._pumping:
            self._again.add(lane_id)
            return
        self._pumping.add(lane_id)
        self._spawn(self._pump(lane_id))

    def kick_all(self) -> None:
        for lane_id in list(self.book.lanes):
            self.kick(lane_id)

    async def _pump(self, lane_id: str) -> None:
        try:
            while True:
                self._again.discard(lane_id)
                await self._once(lane_id)
                if lane_id not in self._again:
                    return
        except Exception:
            pass
        finally:
            self._pumping.discard(lane_id)

    async def _once(self, lane_id: str) -> None:
        lane, q = self.book.lanes[lane_id], self.book.queues[lane_id]
        if lane_id in self.running or not q or not lane.ready() or lane.busy():
            return
        e = self.book.entries[q[0]]
        label = str(e.job.plan.summary.get("model") or e.job.plan.model)
        plan = self.gpu.plan(lane, e.job.plan.model, label)
        if plan.release:
            await self.gpu.release(plan.release, f"for {label}")
            if not q or q[0] != e.job.id or lane_id in self.running or lane.busy():
                return
        q.popleft()
        move(e.job, "running")
        e.started = time.time()
        e.baseline = self.gpu.baseline(lane)
        self.running[lane_id] = e.job.id
        self.gpu.job_started(lane_id)
        self.book.started(e)
        self._spawn(self._run(lane, e))

    def close(self) -> None:
        self.gpu.close()

    # ---------------------------------------------------------------- running a job
    async def _run(self, lane: JobLane, e: Entry) -> None:
        error = None
        try:
            if e.job.plan.prepare is not None and not e.cancel_requested:
                await self._prepare(e)
            if not e.cancel_requested:
                await lane.run(e.job, lambda ev, d: self._event(lane, e, ev, d))
        except Exception as ex:
            error = one_line(str(ex) or type(ex).__name__)
        self.running.pop(lane.id, None)
        self.gpu.loading.pop(lane.id, None)
        if e.cancel_requested:
            state = "cancelled"
        elif error or e.job.error:
            state, e.job.error = "failed", step_line(e, e.job.error or error)
        else:
            state = "done"
        landed = self._kept.pop(e.job.id, {})
        if e.job.plan.finish is not None:             # the job's last step, whatever its end
            try:
                await e.job.plan.finish(landed)
            except Exception as ex:
                if state == "done":
                    state, e.job.error = "failed", one_line(f"Sequence: {one_line(str(ex) or type(ex).__name__)}")
        held = self._held.pop(e.job.id, [])           # a step's file a later step read
        if state == "done":
            self.files.delete([item for item, _ in held])
        for item, d in held if state != "done" else ():
            self._landed(e, item, d)                  # nothing a finished task made is erased
        self.book.finish(e, state)
        self.gpu.job_ended(lane.id)
        self.kick(lane.id)

    async def _prepare(self, e: Entry) -> None:
        """The job's planning step: `prepare` runs as a task `stop` can cancel; its plan, checked as `submit` checks
        one, becomes the job's (the card's summary is now the render's)."""
        def say(text: str) -> None:
            e.phase, e.text = "planning", one_line(text)
            self.book.publish(e)                      # a few lines, each worth seeing: never thinned

        task = asyncio.ensure_future(e.job.plan.prepare(say))   # type: ignore[misc]
        self._planning[e.job.id] = task
        try:
            plan = await task
        except asyncio.CancelledError:
            if e.cancel_requested and task.cancelled():
                return                                # a cancel: the job is cancelled, nothing is rendered
            raise
        finally:
            self._planning.pop(e.job.id, None)
        e.job.plan, e.phase, e.text = checked(e.job.plan, plan), None, None
        self.book.publish(e)

    def stop(self, e: Entry) -> None:
        planning = self._planning.get(e.job.id)
        if planning is not None:
            planning.cancel()
            return
        lane = self.book.lanes.get(e.job.lane or "")
        if lane is not None:
            self._spawn(lane.cancel(e.job.id))

    def _event(self, lane: JobLane, e: Entry, ev: str, d: dict) -> None:
        try:
            handler = getattr(self, f"_ev_{ev}", None)
            if handler is not None and isinstance(d, dict):
                handler(lane, e, d)
        except Exception:
            pass

    def _ev_task(self, lane: JobLane, e: Entry, d: dict) -> None:
        e.job.task, e.step, e.last = int(d.get("task") or 1), 0, None
        self.book.publish(e, progress_only=True)

    def _ev_skip(self, lane: JobLane, e: Entry, d: dict) -> None:
        """A take not needed: the bar jumps past it; its step name is never shown."""
        n = len(e.job.plan.tasks) or 1
        e.job.pct, e.last = max(e.job.pct, min(100, int(100 * int(d.get("task") or 0) / n))), None
        self.book.publish(e, progress_only=True)

    def _ev_model(self, lane: JobLane, e: Entry, d: dict) -> None:
        state, model = d.get("state"), str(d.get("model") or e.job.plan.model)
        if state == "loading":
            self.gpu.loading[lane.id] = model
            e.phase, e.text, e.last = "loading", f"Loading {e.job.plan.summary.get('model') or model}", None
            self.book.publish(e)
            self.gpu.publish()
            return
        self.gpu.loading.pop(lane.id, None)
        self.gpu.changed()

    def _ev_progress(self, lane: JobLane, e: Entry, d: dict) -> None:
        j, n = e.job, len(e.job.plan.tasks)
        task, steps, step = int(d.get("task") or j.task or 1), int(d.get("steps") or 0), int(d.get("step") or 0)
        phase, now = str(d.get("phase") or ""), self.clock()
        j.task, e.phase, e.step, e.steps, e.text = task, phase, step, steps, d.get("text")
        if steps > 0 and "load" not in phase:
            done = (task - 1) * steps + step
            if e.last and (e.last[2], e.last[3]) == (task, phase) and done > e.last[1]:
                e.acc_s += now - e.last[0]
                e.acc_steps += done - e.last[1]
            e.last, e.done_steps = (now, done, task, phase), done
            if e.acc_steps >= 1 and done >= 2:
                j.eta_s = round(e.acc_s / e.acc_steps * (n * steps - done), 1)
        else:
            e.last = None
        pct = d.get("pct")
        if not isinstance(pct, (int, float)):
            pct = 100 * e.done_steps / (n * steps or 1)
        j.pct = max(0, min(100, int(pct)))
        self.book.publish(e, progress_only=True)

    def _ev_output(self, lane: JobLane, e: Entry, d: dict) -> None:
        item = d.get("item")
        if not isinstance(item, str) or self.files.kind(item) is None:
            return
        if d.get("between"):                          # for the next step: off the job and Media while it runs
            self._held.setdefault(e.job.id, []).append((item, d))
            return
        if isinstance(d.get("task"), int):
            self._kept.setdefault(e.job.id, {})[d["task"]] = item
        self._landed(e, item, d)

    def _landed(self, e: Entry, item: str, d: dict) -> None:
        kind = self.files.kind(item)
        e.job.outputs.append(item)
        w, h, s = d.get("w"), d.get("h"), d.get("seconds")
        length = {"seconds": s if isinstance(s, (int, float)) else None} if kind in ("clip", "sound") else {}
        self.bus.publish("media", "generation", {"item": {     # a clip or sound: no thumbnail, its length in seconds
            "id": item, "kind": kind, "url": self.files.url(item), "thumb": self.files.thumb_url(item),
            "w": w if isinstance(w, int) else None, "h": h if isinstance(h, int) else None, "created": time.time(),
            "job": e.job.id, **length}})
        self.book.publish(e)

    def _ev_task_done(self, lane: JobLane, e: Entry, d: dict) -> None:
        if d.get("ok") is False:
            e.job.error = one_line(d.get("error"))
        if isinstance(d.get("judge"), dict):           # a judge's verdict on this task
            e.job.notes.setdefault("judged", {})[str(d.get("task"))] = d["judge"]
        task, judge = d.get("task"), e.job.plan.judge
        if judge is not None and isinstance(task, int) and jobgraph.where(e.job.plan, task):
            take = judge.done(task, d)
            if take is not None:
                e.job.takes[task] = take
                e.job.notes.setdefault("takes", {})[str(task)] = {"passes": take.passes, "line": take.line}
        peak, model = d.get("peak_vram_mb"), e.job.plan.model
        if isinstance(peak, int) and peak > 0 and model != NO_MODEL:      # a join loads no model: nothing learned
            base = e.baseline or 0
            self.gpu.learn("vram", model, lane.gpu_uuid, peak - base if peak > base else peak)

    def _ev_error(self, lane: JobLane, e: Entry, d: dict) -> None:
        if d.get("fatal", True):
            e.job.error = one_line(d)
