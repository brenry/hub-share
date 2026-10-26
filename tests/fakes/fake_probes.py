"""Scripted NVML readings that count every GPU read (decision points only)."""
from __future__ import annotations

import copy

GB = 1024


class FakeProbes:
    """Same surface as `hub.core.probes.Probes`. Mutate `gpu_list` (or `set_procs`) between steps."""

    def __init__(self, total_mb: int = 32 * GB, uuid: str = "GPU-fake-0", name: str = "Fake RTX") -> None:
        self.gpu_list: list[dict] | None = [{"index": 0, "uuid": uuid, "name": name, "total_mb": total_mb,
                                             "used_mb": 0, "free_mb": total_mb, "procs": {}}]
        self.reads = 0

    def set_procs(self, procs: dict[int, int], index: int = 0) -> None:
        """Set which processes use the GPU (pid -> MB); used/free follow."""
        assert self.gpu_list is not None
        g = self.gpu_list[index]
        g["procs"] = dict(procs)
        g["used_mb"] = sum(procs.values())
        g["free_mb"] = g["total_mb"] - g["used_mb"]

    def gpus(self) -> list[dict] | None:
        self.reads += 1
        return copy.deepcopy(self.gpu_list)
