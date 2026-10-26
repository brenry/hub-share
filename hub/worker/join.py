"""A join (the Edit Video tab's Save): one MP4 or WAV of a sequence, made by ffmpeg in the worker (never in the
controller). Stdlib only.

`run(job, task, request, send, loaded, state)` takes the sequence module's request (`joincmd`), finds ffmpeg and
ffprobe (`FFMPEG_BINARY`/`FFPROBE_BINARY` when the adapter's `prepare` named them, else on PATH), probes each clip
once (an MP4), asks ffmpeg once per worker whether its `amix` has `normalize` (when track 2 holds something), runs
the command `joincmd.build` gives with the worker's own death signal, reports `-progress` as the join's frames,
checks the file's length with the Hub's own readers (`hub/core/clip.py` for an MP4, `hub/core/sound.py` for a WAV,
loaded by their paths as `probe.py` does) and sends one `output`; it returns the `task_done`. `cancel(job)` stops
ffmpeg (SIGTERM, then SIGKILL after `KILL_AFTER` seconds), or refuses the join's start when it arrives first. No model
is loaded or freed: `task_done.model` is the one the engine held before (`loaded`).
"""
from __future__ import annotations

import contextlib
import ctypes
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

try:
    from . import faults, joincmd, mixcmd, probe
except ImportError:  # run as a script by the engine's Python
    import faults
    import joincmd
    import mixcmd
    import probe

NO_FFMPEG = "ffmpeg is not installed on the server"       # the fork adapter's line (a test pins the equality)
GONE = "A clip of the sequence is gone"
NO_DUCK = "This ffmpeg cannot duck a sound under track 1 (no sidechaincompress); turn Duck off on the item"
SOUND_SLACK = 0.05                                         # a WAV's seconds may differ by this much per item
KILL_AFTER = 5.0
PROBE_SECONDS = 60
Send = Callable[[dict[str, Any]], None]

_lock = threading.Lock()
_running: dict[str, subprocess.Popen] = {}
_stopped: set[str] = set()                                 # joins whose ffmpeg a cancel stopped
_pending: str | None = None                                # a cancel that came before its ffmpeg started
_reader: Any = None
_sound_reader: Any = None
_normalize: bool | None = None                             # whether this ffmpeg's `amix` has `normalize`
_duck: bool | None = None                                  # whether it has `sidechaincompress`
try:
    _prctl: Any = ctypes.CDLL(None, use_errno=True).prctl
except (OSError, AttributeError):
    _prctl = None


class Failed(Exception):
    """The join's one line, and its stage."""

    def __init__(self, text: str, stage: str = "runtime") -> None:
        super().__init__(text)
        self.stage = stage


def _die_with_worker() -> None:
    """In ffmpeg's child before exec: it gets SIGKILL when the worker goes (as `main.die_with_parent`)."""
    if _prctl is not None:
        _prctl(1, signal.SIGKILL)                          # PR_SET_PDEATHSIG


def programs() -> tuple[str, str]:
    """ffmpeg and ffprobe: as the adapter named them, else on PATH; either missing is the one refusal."""
    found = [os.environ.get(env) or shutil.which(name) for env, name in
             (("FFMPEG_BINARY", "ffmpeg"), ("FFPROBE_BINARY", "ffprobe"))]
    if not all(found):
        raise Failed(NO_FFMPEG)
    return str(found[0]), str(found[1])


def reader() -> Any:
    global _reader
    if _reader is None:
        _reader = probe.clip_reader()
    return _reader


def sound_reader() -> Any:
    """`hub/core/sound.py`, loaded from its file beside the clip reader (it imports the stdlib alone)."""
    global _sound_reader
    if _sound_reader is None:
        spec = importlib.util.spec_from_file_location("hub_join_sound", Path(probe.CLIP_READER).with_name("sound.py"))
        if spec is None or spec.loader is None:
            raise RuntimeError("The Hub's sound reader is not beside the worker")
        _sound_reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_sound_reader)
    return _sound_reader


def amix_normalize(ffmpeg: str) -> bool:
    """Whether the installed ffmpeg's `amix` takes `normalize` (its help names it); asked once per worker."""
    global _normalize
    if _normalize is None:
        try:
            done = subprocess.run([ffmpeg, "-hide_banner", "-h", "filter=amix"], capture_output=True, text=True,
                                  timeout=PROBE_SECONDS, preexec_fn=_die_with_worker)
            _normalize = "normalize" in done.stdout
        except (OSError, subprocess.TimeoutExpired):
            _normalize = False
    return _normalize


def can_duck(ffmpeg: str) -> bool:
    """Whether the installed ffmpeg has `sidechaincompress`; asked once per worker."""
    global _duck
    if _duck is None:
        try:
            done = subprocess.run([ffmpeg, "-hide_banner", "-h", "filter=sidechaincompress"], capture_output=True,
                                  text=True, timeout=PROBE_SECONDS, preexec_fn=_die_with_worker)
            _duck = "sidechaincompress" in done.stdout and "threshold" in done.stdout
        except (OSError, subprocess.TimeoutExpired):
            _duck = False
    return _duck


def probe_one(ffprobe: str, path: str) -> dict[str, Any]:
    """The input's stream facts (`joincmd.facts`); a probe that fails or prints no JSON gives none (encode path)."""
    try:
        done = subprocess.run(joincmd.probe_argv(ffprobe, path), capture_output=True, text=True,
                              timeout=PROBE_SECONDS, preexec_fn=_die_with_worker)
        return joincmd.facts(json.loads(done.stdout) if done.returncode == 0 else None)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return joincmd.facts(None)


def prepare(job: str, request: dict[str, Any], state: str) -> tuple[joincmd.Command, list[dict[str, Any]]]:
    """The command for this join and each input's facts; refused when ffmpeg is missing or an input is gone."""
    ffmpeg, ffprobe = programs()
    if request.get("lanes"):                               # a mix, its checks in `mixcmd`
        try:
            return mixcmd.prepare(job, request, state, ffmpeg, amix_normalize), []
        except ValueError as exc:
            raise Failed(str(exc)) from None
    items, placed = list(request.get("items") or []), list(request.get("audio") or [])
    if not items and not placed:
        raise Failed("The sequence is empty")
    if not all(os.path.isfile(str(i.get("path"))) for i in [*items, *placed]):
        raise Failed(GONE)
    wav = request.get("out_kind", "mp4") == "wav"
    probed = [] if wav else [probe_one(ffprobe, str(i["path"])) for i in items]
    normalize = amix_normalize(ffmpeg) if placed else True
    if any(p.get("duck") for p in placed) and not can_duck(ffmpeg):
        raise Failed(NO_DUCK)
    try:
        return joincmd.build(request, probed, ffmpeg, state, job, normalize), probed
    except ValueError as exc:
        raise Failed(str(exc)) from None


def _stop(proc: subprocess.Popen) -> None:
    with contextlib.suppress(OSError):
        proc.terminate()
    try:
        proc.wait(KILL_AFTER)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(OSError):
            proc.kill()


def cancel(job: str) -> None:
    """Stop the join `job`'s ffmpeg; before it starts, the join will not start. Never blocks the caller."""
    global _pending
    with _lock:
        proc = _running.get(job)
        if proc is None:
            _pending = job
            return
        _stopped.add(job)
    threading.Thread(target=_stop, args=(proc,), daemon=True).start()


def _start(job: str, cmd: joincmd.Command, err: Any) -> subprocess.Popen | None:
    """ffmpeg started and recorded for `cancel`; None when a cancel for this job came first."""
    global _pending
    with _lock:
        cancelled, _pending = _pending == job, None
        if cancelled:
            return None
        proc = subprocess.Popen(cmd.argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=err, text=True,
                                preexec_fn=_die_with_worker)
        _running[job] = proc
        return proc


def _last_line(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = [ln.strip() for ln in f.read().splitlines() if ln.strip()]
    except OSError:
        lines = []
    return lines[-1][:200] if lines else ""


def _execute(job: str, cmd: joincmd.Command, base: dict[str, Any], send: Send) -> None:
    """ffmpeg run to its end, its progress sent; raises Failed (cancelled, a non-zero exit, a wrong length)."""
    err_file = os.path.join(os.path.dirname(cmd.list_file), f"join-{job}.err")
    try:
        if cmd.listing is not None:
            with open(cmd.list_file, "w", encoding="utf-8") as f:
                f.write(cmd.listing)
        os.makedirs(os.path.dirname(cmd.out), exist_ok=True)
        with open(err_file, "wb") as err:
            proc = _start(job, cmd, err)
        if proc is None:
            raise Failed("Cancelled", "cancelled")
        try:
            for line in proc.stdout or ():
                key, _, value = line.strip().partition("=")
                if key == "out_time_us" and value.strip().isdigit():
                    send({**base, "ev": "progress", "phase": "joining", "step": round(int(value) / 1e6 * cmd.fps),
                          "steps": cmd.expect, "text": ""})
            code = proc.wait()
        finally:
            if proc.poll() is None:                        # this thread failed while ffmpeg ran: it goes too
                proc.kill()
                proc.wait()
            with _lock:
                _running.pop(job, None)
                stopped = job in _stopped
                _stopped.discard(job)
        if stopped:
            raise Failed("Cancelled", "cancelled")
        if code != 0:
            raise Failed(_last_line(err_file) or f"ffmpeg stopped with code {code}")
        then = getattr(cmd, "then", None)                  # a mix's master runs after its pre-master
        _execute(job, then(err_file), base, send) if then is not None else check(cmd)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(cmd.out)
        raise
    finally:
        for path in (cmd.list_file, err_file):
            with contextlib.suppress(OSError):
                os.unlink(path)


def check(cmd: joincmd.Command) -> None:
    """The joined file's frames within one per item of the expected ones; a WAV's seconds within
    `SOUND_SLACK` per item."""
    if cmd.kind == "wav":
        try:
            seconds = float(sound_reader().facts(Path(cmd.out))["seconds"])
        except (OSError, ValueError, KeyError) as exc:
            raise Failed(f"The saved sound cannot be read: {exc}") from None
        if abs(seconds - cmd.seconds) > SOUND_SLACK * max(1, cmd.n):
            raise Failed(f"The saved sound came out {seconds:.1f} s instead of {cmd.seconds:.1f} s")
        return
    try:
        got = reader().facts(cmd.out)
    except (OSError, ValueError) as exc:
        raise Failed(f"The joined clip cannot be read: {exc}") from None
    if abs(int(got["frames"]) - cmd.expect) > cmd.n:
        raise Failed(f"The joined clip came out {got['seconds']:.1f} s ({got['frames']} frames) instead of "
                     f"{cmd.expect / cmd.fps:.1f} s ({cmd.expect} frames)")


def run(job: str, task: int, request: dict[str, Any], send: Send, loaded: str | None, state: str,
        told: Callable[[joincmd.Command, list[dict[str, Any]]], None] | None = None) -> dict[str, Any]:
    """One join to its end (blocking): progress and the one `output` through `send`; returns `task_done`.
    `told` (the probe's) hears the command and the inputs' facts before ffmpeg starts."""
    started = time.monotonic()
    base = {"job": job, "task": task}
    error: dict[str, str] | None = None
    try:
        cmd, probed = prepare(job, request, os.path.abspath(state))
        if told is not None:
            told(cmd, probed)
        _execute(job, cmd, base, send)
        send({**base, "ev": "output", "file": os.path.abspath(cmd.out)})
    except Failed as exc:
        error = faults.failure([], True) if exc.stage == "cancelled" else {"stage": exc.stage, "text": str(exc)}
    except Exception as exc:
        error = {"stage": "runtime", "text": ((str(exc).strip().splitlines() or [type(exc).__name__])[0])[:200]}
    done = {**base, "ev": "task_done", "ok": error is None, "seconds": round(time.monotonic() - started, 2),
            "model": loaded, "peak_vram_mb": None, "peak_rss_mb": None}
    if error is not None:
        done["error"] = error
    return done
