"""A continue whose source clip's sound ends before its last frame. Stdlib only.

Upstream joins a continue's sound across the overlap: it measures the source's sound under the overlap and adds
the shortfall to the stretch it re-makes (`shared/utils/audio_video.py`, `audio_overlap_repair_seconds`), and a
family that re-makes only the last overlap frame's sound refuses when that stretch reaches past one frame ("the
source soundtrack ends too early to repair this join", in that family's pipeline). Such a family's own clips can
end that way: the engine cuts a pass's sound to its frames and never pads it (`wgp.py:8523`), so a clip continued
once may not continue again.

So before a continue of a model whose catalog entry carries `sound_join` (the facts file: the frames whose sound
its join makes again, with the definition's `audio_overlap_repair_ms`), the worker measures the source: its frames
from the Hub's own MP4 reader (`hub/core/clip.py`), its sound by decoding it with the ffmpeg the engine would use
(to memory: nothing is written). Only when the engine would refuse it (the sound short of the last frame by more
than those frames less the repair), and by no more frames than the overlap, the task keeps the fewest frames off
the end that make the join fit: the engine's own `keep_frames_video_source`, negative for frames off the end
(`wgp.py:1357`; `shared/utils/utils.py`, `get_resampled_video_transparent`). Otherwise the task goes as it was.
"""
from __future__ import annotations

import importlib.util
import math
import os
import shutil
import subprocess
from collections.abc import Callable
from types import ModuleType
from typing import Any

KEY, SOURCE, OVERLAP = "keep_frames_video_source", "video_source", "sliding_window_overlap"
RATE = 48000                 # the decode's sample rate: one sample is 0.02 ms
MARGIN = 0.001               # seconds kept clear of the engine's limit (its own sample rounding)
SECONDS = 60                 # a decode that takes longer is given up (the task goes as it was)
CLIP_READER = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, "core", "clip.py")
Measure = Callable[[str], "float | None"]
_reader: ModuleType | None = None


def reader() -> ModuleType:
    """`hub/core/clip.py`, loaded from its file as the worker's probe does (it imports the stdlib alone)."""
    global _reader
    if _reader is None:
        spec = importlib.util.spec_from_file_location("hub_soundtail_clip", CLIP_READER)
        if spec is None or spec.loader is None:
            raise OSError("The Hub's clip reader is not beside the worker")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _reader = module
    return _reader


def ffmpeg() -> str | None:
    """The engine's own search (`shared/utils/video_decode.py`, `_resolve_media_binary`): FFMPEG_BINARY, the
    engine's `ffmpeg_bins` (the worker runs in the engine's folder), then PATH."""
    named = os.environ.get("FFMPEG_BINARY", "")
    if named and os.path.isfile(named):
        return named
    bundled = os.path.join(os.getcwd(), "ffmpeg_bins", "ffmpeg")
    return bundled if os.path.isfile(bundled) else shutil.which("ffmpeg")


def sound_seconds(path: str) -> float | None:
    """How long the first sound track plays, decoded as the engine decodes it (None: none, or no answer)."""
    program = ffmpeg()
    if program is None:
        return None
    argv = [program, "-nostdin", "-v", "error", "-i", path, "-map", "0:a:0", "-ac", "1", "-ar", str(RATE),
            "-f", "s16le", "-"]
    try:
        done = subprocess.run(argv, capture_output=True, timeout=SECONDS, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return len(done.stdout) / 2 / RATE if done.returncode == 0 and done.stdout else None


def cover(task: dict[str, Any], video: dict[str, Any], measure: Measure | None = None) -> dict[str, Any]:
    """`task`, keeping fewer source frames when the model's join would refuse the source's sound (`video`: the
    model's catalog facts, `fps` and `sound_join`)."""
    join, fps = video.get("sound_join") or {}, video.get("fps")
    path, overlap = task.get(SOURCE), task.get(OVERLAP)
    if not join.get("frames") or not fps or not isinstance(path, str) or not path or task.get(KEY) \
            or not isinstance(overlap, int):
        return task
    allowed = join["frames"] / fps - float(join.get("repair_ms") or 0) / 1000 - MARGIN   # seconds short it takes
    try:
        facts = reader().facts(path)
    except (OSError, ValueError):
        return task
    if allowed < 0 or not facts.get("audio") or not facts.get("frames") or not facts.get("fps"):
        return task
    sound = (measure or sound_seconds)(path)
    if sound is None:
        return task
    frames = facts["frames"] / facts["fps"] * fps               # the source as the engine resamples it
    drop = math.ceil(frames - math.floor((sound + allowed) * fps + 1e-9) - 1e-9)
    return {**task, KEY: str(-drop)} if 0 < drop <= overlap else task


def dropped(task: dict[str, Any]) -> int:
    """The source frames a continue task leaves off the end (`cover`)."""
    value = str(task.get(KEY) or "")
    return -int(value) if value.lstrip("-").isdigit() and int(value) < 0 else 0
