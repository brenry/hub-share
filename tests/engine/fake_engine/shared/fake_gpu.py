"""The fake engine's GPU: a stand-in `torch.cuda` with the calls the worker's peak meter makes (one card; a loaded
model holds `PICTURE_MB` or, for a clip model, `CLIP_MB` above the CUDA context), and the engine's own record of what
it did, one line each, for the tests to read the order: `start` (this process imported the engine), `load <model>`,
`release`. The record is kept only when a test put an empty one in the config folder the hub gives the engine (never
in the engine root)."""
from __future__ import annotations

import argparse
import os
import sys
import types

MB = 1024 * 1024
TOTAL_MB, CONTEXT_MB = 24_576, 400
PICTURE_MB, CLIP_MB = 9_000, 20_000
RECORD = "fake_engine_record.txt"


class Cuda:
    def __init__(self) -> None:
        self.held, self.peak = 0, 0              # MB the engine's allocator holds now / at most since the last reset

    def hold(self, mb: int) -> None:
        self.held, self.peak = mb, max(self.peak, mb)

    def mem_get_info(self) -> tuple[int, int]:
        return (TOTAL_MB - CONTEXT_MB - self.held) * MB, TOTAL_MB * MB

    def memory_reserved(self) -> int:
        return self.held * MB

    def max_memory_reserved(self) -> int:
        return self.peak * MB

    def reset_peak_memory_stats(self) -> None:
        self.peak = self.held


cuda = Cuda()
if "torch" not in sys.modules:                   # the real one, if the engine's Python has it and loaded it, stays
    sys.modules["torch"] = types.SimpleNamespace(cuda=cuda)
_record: str | None = None


def open_record(args: argparse.Namespace) -> argparse.Namespace:
    global _record
    path = os.path.join(os.path.abspath(args.config), RECORD) if args.config else ""
    _record = path if os.path.isfile(path) else None
    note("start")
    return args


def note(line: str) -> None:
    if _record is not None:
        with open(_record, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def load(model: str, clip: bool) -> tuple[object, str]:
    """The engine's (wan_model, transformer_type) once `model` is in memory."""
    cuda.hold(CLIP_MB if clip else PICTURE_MB)
    note(f"load {model}")
    return object(), model


def release() -> None:
    """The engine's release_model: its own swap frees the model (the engine's `wan_model` becomes None)."""
    if cuda.held:
        note("release")
    cuda.hold(0)
