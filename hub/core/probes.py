"""Read-only GPU facts from NVML, only when asked (at decision points).

NVML is a management library: it creates no CUDA context and runs no nvidia-smi.
"""
from __future__ import annotations

from typing import Any

MB = 1024 * 1024


class Probes:
    """The real probes. `gpus()` returns None when NVML is unavailable (no driver/library)."""

    def __init__(self) -> None:
        self._nvml: Any = None

    def _lib(self) -> Any:
        if self._nvml is None:
            import pynvml

            pynvml.nvmlInit()
            self._nvml = pynvml
        return self._nvml

    def gpus(self) -> list[dict] | None:
        """[{index, uuid, name, total_mb, used_mb, free_mb, procs: {pid: mb}}] or None."""
        try:
            nv = self._lib()
            out = []
            for i in range(nv.nvmlDeviceGetCount()):
                h = nv.nvmlDeviceGetHandleByIndex(i)
                mem = nv.nvmlDeviceGetMemoryInfo(h)
                procs: dict[int, int] = {}
                for getter in (nv.nvmlDeviceGetComputeRunningProcesses, nv.nvmlDeviceGetGraphicsRunningProcesses):
                    for p in getter(h):
                        used = p.usedGpuMemory if isinstance(p.usedGpuMemory, int) else 0
                        procs[p.pid] = max(procs.get(p.pid, 0), used // MB)
                total, free = mem.total // MB, mem.free // MB
                out.append({"index": i, "uuid": _text(nv.nvmlDeviceGetUUID(h)), "name": _text(nv.nvmlDeviceGetName(h)),
                            "total_mb": total, "used_mb": total - free, "free_mb": free, "procs": procs})
            return out
        except Exception:
            self._nvml = None
            return None


def _text(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)
