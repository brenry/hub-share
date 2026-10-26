"""Frames of a clip at full size: the views of a character's orbit, made by ffmpeg in the worker (never
in the controller). Stdlib only; nothing on stdout.

`run(job, task, request, send, loaded, state)` takes a frames request (`FramesRequest`: the clip, the 0-based frame
indices), finds ffmpeg and ffprobe as a join does (`join.programs`), counts the clip's frames with ffprobe and refuses a
clip shorter than the last index needs (`SHORT`), then runs ffmpeg once, `select` keeping exactly those frames,
`-fps_mode passthrough` so none is doubled or dropped, each written as a PNG at the clip's own size into the outbox. One
`output` per index, in the request's order; it returns the `task_done`. ffmpeg runs in the join's registry
(`join._start`), so `join.cancel(job)` (the worker's `cancel`) stops it, or keeps it from starting. No model is loaded
or freed: `task_done.model` is the one the engine held before (`loaded`). No decode here is scaled (the judges' is,
`faces.py`, to 640).
"""
from __future__ import annotations

import contextlib
import os
import subprocess
import time
from collections.abc import Callable
from typing import Any

try:
    from . import join
except ImportError:  # run as a script by the engine's Python
    import join

SHORT = "The orbit has {} frames; the views need {}"
GONE = "The clip to take frames from is gone"
NONE_ASKED = "No frames were asked for"
TWICE = "A frame is asked for twice"
BELOW = "A frame is counted from 0"
UNREAD = "The clip's frames could not be counted"
SECONDS = 300
Send = Callable[[dict[str, Any]], None]


def count(ffprobe: str, path: str) -> int:
    """The clip's video frames, its packets counted (no decode); refused in one line when ffprobe cannot read it."""
    argv = [ffprobe, "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
            "stream=nb_read_packets", "-of", "csv=p=0", path]
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=SECONDS, preexec_fn=join._die_with_worker)
        return int(done.stdout.strip().splitlines()[0].strip().rstrip(","))
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        raise join.Failed(UNREAD) from None


def select(indices: list[int]) -> str:
    """The filter that keeps exactly those frames: `select='eq(n,2)+eq(n,21)+…'`."""
    return "select='" + "+".join(f"eq(n,{n})" for n in sorted(indices)) + "'"


def argv(ffmpeg: str, clip: str, indices: list[int], pattern: str) -> list[str]:
    """One ffmpeg run: the frames kept, none doubled or dropped, each a PNG at the clip's size (`pattern` numbers
    them from 1 in frame order)."""
    return [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", clip, "-vf", select(indices),
            "-fps_mode", "passthrough", "-frames:v", str(len(indices)), pattern]


class _Command:
    """What `join._start` reads of a command: its argv."""

    def __init__(self, argv: list[str]) -> None:
        self.argv = argv


def _ffmpeg(job: str, argv: list[str]) -> tuple[int, str]:
    """ffmpeg run to its end in the join's registry (`join.cancel` stops it): its exit code and its stderr; a cancel
    is `join.Failed` of stage "cancelled"."""
    proc = join._start(job, _Command(argv), subprocess.PIPE)
    if proc is None:
        raise join.Failed("Cancelled", "cancelled")
    try:
        try:
            _, err = proc.communicate(timeout=SECONDS)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise join.Failed(f"ffmpeg took more than {SECONDS} s to take the frames") from None
    finally:
        with join._lock:
            join._running.pop(job, None)
            stopped = job in join._stopped
            join._stopped.discard(job)
    if stopped:
        raise join.Failed("Cancelled", "cancelled")
    return proc.returncode, err or ""


def _last_line(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1][:200] if lines else ""


def extract(job: str, task: int, request: dict[str, Any], state: str) -> list[str]:
    """The frames as PNG files in the outbox, one per index in the request's order; raises `join.Failed`."""
    clip, indices = str(request.get("clip") or ""), [int(n) for n in request.get("frames") or []]
    if not indices:
        raise join.Failed(NONE_ASKED)
    if len(set(indices)) != len(indices):
        raise join.Failed(TWICE)
    if min(indices) < 0:
        raise join.Failed(BELOW)
    if not os.path.isfile(clip):
        raise join.Failed(GONE)
    ffmpeg, ffprobe = join.programs()
    have, need = count(ffprobe, clip), max(indices) + 1
    if have < need:
        raise join.Failed(SHORT.format(have, need))
    outbox = os.path.join(state, "outbox")
    os.makedirs(outbox, exist_ok=True)
    stem = os.path.join(outbox, f"frames-{job}-{task}")
    made = [f"{stem}-{k}.png" for k in range(1, len(indices) + 1)]
    try:
        code, err = _ffmpeg(job, argv(ffmpeg, clip, indices, f"{stem}-%d.png"))
        if code != 0 or not all(os.path.isfile(p) for p in made):
            got = sum(os.path.isfile(p) for p in made)
            raise join.Failed(_last_line(err) or f"ffmpeg wrote {got} of {len(indices)} frames")
    except BaseException:
        for p in made:
            with contextlib.suppress(OSError):
                os.unlink(p)
        raise
    order = sorted(indices)
    return [made[order.index(n)] for n in indices]


def run(job: str, task: int, request: dict[str, Any], send: Send, loaded: str | None, state: str) -> dict[str, Any]:
    """One frames request to its end (blocking): one `output` per frame through `send`; returns `task_done`."""
    started = time.monotonic()
    base = {"job": job, "task": task}
    error: dict[str, str] | None = None
    try:
        for path in extract(job, task, request, os.path.abspath(state)):
            send({**base, "ev": "output", "file": os.path.abspath(path)})
    except join.Failed as exc:
        error = join.faults.failure([], True) if exc.stage == "cancelled" else {"stage": exc.stage, "text": str(exc)}
    except Exception as exc:
        error = {"stage": "runtime", "text": ((str(exc).strip().splitlines() or [type(exc).__name__])[0])[:200]}
    done = {**base, "ev": "task_done", "ok": error is None, "seconds": round(time.monotonic() - started, 2),
            "model": loaded, "peak_vram_mb": None, "peak_rss_mb": None}
    if error is not None:
        done["error"] = error
    return done
