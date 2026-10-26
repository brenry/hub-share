"""Shared setup for the sequence tests: clips landed as the engine lands them (`clips/<day>/<time>.mp4`, a tiny MP4
whose boxes say its size, rate, frames and sound), and the path of a sequence's file."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.fakes.mp4 import tiny_mp4
from tests.fakes.wav import tiny_wav

DAY = "2026-10-14"


def clip(files: Any, stem: str, *, frames: int = 124, fps: int = 24, w: int = 960, h: int = 544,
         audio: bool = False) -> str:
    """A clip in the clips root; -> its id."""
    path = files.roots["clips"] / DAY / f"{stem}.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(tiny_mp4(w=w, h=h, fps=fps, frames=frames, audio=audio))
    return f"clips/{DAY}/{stem}.mp4"


def seq_path(files: Any, name: str) -> Path:
    return files.roots["clips"] / "sequences" / f"{name}.json"


def whole(item: str, frames: int = 124) -> dict:
    return {"clip": item, "in": 0, "out": frames}


def sound(files: Any, stem: str, *, seconds: float = 2.0) -> str:
    """A sound in the sounds root (a tiny WAV of `seconds`); -> its id."""
    path = files.roots["sounds"] / DAY / f"{stem}.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(tiny_wav(seconds=seconds))
    return f"sounds/{DAY}/{stem}.wav"


def two(t1: list, t2: list | None = None) -> list:
    """Both tracks, the second empty unless given."""
    return [t1, t2 or []]
