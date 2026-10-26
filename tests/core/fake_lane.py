"""A scripted image lane for core tests (no GPU, no worker)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from PIL import Image

from hub.core.api import Job, Resident
from tests.fakes.fake_probes import FakeProbes
from tests.fakes.mp4 import tiny_mp4


class FakeLane:
    """A JobLane that 'loads' a model by adding MB to FakeProbes and writes tiny PNG outputs (`video`: MP4 clips
    into the clips root beside the outputs)."""

    kind = "image"

    def __init__(self, outputs: Path, probes: FakeProbes, lane_id: str = "image.gpu0", uuid: str = "GPU-fake-0",
                 pid: int = 4242, steps: int = 4, step_s: float = 0.0, model_mb: int = 12_000) -> None:
        self.id, self.gpu_uuid, self.pid = lane_id, uuid, pid
        self.outputs, self.probes = outputs, probes
        self.steps, self.step_s, self.model_mb = steps, step_s, model_mb
        self.model: str | None = None
        self.is_ready, self._busy = True, False
        self.gate: asyncio.Event | None = None
        self.fail_at: int | None = None
        self.judge: dict | None = None               # a judge's verdict every task_done carries
        self.video = False
        self.released: list[str] = []
        self.cancelled: set[str] = set()
        self.runs: list[str] = []
        self.on_change = lambda: None

    def _usage(self, mb: int) -> None:
        procs = dict((self.probes.gpu_list or [{}])[0].get("procs", {}))
        if mb:
            procs[self.pid] = mb
        else:
            procs.pop(self.pid, None)
        self.probes.set_procs(procs)

    def residency(self) -> list[Resident]:
        return [Resident(self.model)] if self.model else []

    def busy(self) -> bool:
        return self._busy

    def pids(self) -> list[int]:
        return [self.pid]

    def ready(self) -> bool:
        return self.is_ready

    async def release(self, reason: str) -> bool:
        if self._busy:
            return False
        self.released.append(reason)
        self.model = None
        self._usage(0)
        return True

    def reset(self) -> None:
        self.is_ready = True

    async def stop(self) -> None:
        self.released.append("stop")
        self.model = None
        self._usage(0)

    async def cancel(self, job_id: str) -> None:
        self.cancelled.add(job_id)
        if self.gate is not None:
            self.gate.set()

    async def run(self, job: Job, emit) -> None:  # type: ignore[no-untyped-def]
        self._busy = True
        self.runs.append(job.id)
        n = len(job.plan.tasks)
        try:
            for k in range(1, n + 1):
                if job.id in self.cancelled:
                    raise RuntimeError("Cancelled")
                emit("task", {"task": k, "of": n})
                if self.model != job.plan.model:
                    emit("model", {"state": "loading", "model": job.plan.model})
                    self.model = job.plan.model
                    self._usage(self.model_mb)
                    emit("model", {"state": "loaded", "model": job.plan.model})
                for s in range(1, self.steps + 1):
                    if self.gate is not None:
                        await self.gate.wait()
                        if job.id in self.cancelled:
                            raise RuntimeError("Cancelled")
                    await asyncio.sleep(self.step_s)
                    emit("progress", {"task": k, "of": n, "phase": "inference", "step": s, "steps": self.steps,
                                      "pct": int((k - 1 + s / self.steps) / n * 100), "text": "Denoising"})
                if self.fail_at == k:
                    raise RuntimeError("Out of GPU memory\ndetails nobody needs")
                if self.video:
                    self._clip(job.id, k, emit)
                    continue
                folder = self.outputs / "2026-10-09"
                folder.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (64, 48), (k * 40, 90, 120)).save(folder / f"{job.id}_{k}.png")
                emit("output", {"task": k, "item": f"out/2026-10-09/{job.id}_{k}.png", "w": 64, "h": 48})
                emit("task_done", {"task": k, "seconds": 0.1, "peak_vram_mb": 14_000, "peak_rss_mb": 9_000,
                                   **({"judge": self.judge} if self.judge else {})})
        finally:
            self._busy = False

    def _clip(self, job_id: str, k: int, emit) -> None:  # type: ignore[no-untyped-def]
        folder = self.outputs.parent / "clips" / "2026-10-09"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{job_id}_{k}.mp4").write_bytes(tiny_mp4())
        emit("output", {"task": k, "item": f"clips/2026-10-09/{job_id}_{k}.mp4", "kind": "clip", "w": None, "h": None})
        emit("task_done", {"task": k, "seconds": 0.1, "peak_vram_mb": 14_000, "peak_rss_mb": 9_000})

