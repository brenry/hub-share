"""Spawn, watch and stop one engine worker: a child process on a socketpair (NDJSON).

The worker runs the engine's own Python with a clean, offline environment. It dies with
the controller (PDEATHSIG, and EOF on its socket). Crashes restart lazily with backoff
(2 s, 10 s, 30 s); three crashes in ten minutes, or any failure while starting, leave it
`down` until `reset()`.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import socket
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hub.core import enginescope
from hub.settings import ENGINE_OWN, SAME
from hub.worker import protocol

WORKER = Path(__file__).resolve().parent.parent / "worker" / "main.py"
BACKOFF_S = (2.0, 10.0, 30.0)
CRASH_WINDOW_S = 600.0
MAX_CRASHES = 3
OTHER_PROTO = "The engine's worker speaks protocol {}; the Hub speaks {} (install the Hub again)"


class EngineFailed(RuntimeError):
    """stage: validation | generation | cancelled | runtime | oom | crashed; text: one plain line."""

    def __init__(self, stage: str, text: str) -> None:
        super().__init__(text)
        self.stage, self.text = stage, text


def worker_env(home: Path, visible_gpu: str, engine: Mapping[str, Any] | None = None) -> dict[str, str]:
    """A clean environment: nothing inherited but PATH (and the library path, if set). PATH always holds the system
    program folders, where the worker looks for ffmpeg before the engine would fetch it; TMPDIR is in its home, so the
    engine's temps stay in data/. The compilers its kernels build with are its CC and CXX."""
    path = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    path += [p for p in ("/usr/local/bin", "/usr/bin", "/bin") if p not in path]
    env = {"PATH": os.pathsep.join(path), "HOME": str(home), "TMPDIR": str(home / "tmp"), "LANG": "C.UTF-8",
           "CUDA_DEVICE_ORDER": "PCI_BUS_ID", "CUDA_VISIBLE_DEVICES": visible_gpu, **protocol.OFFLINE_ENV}
    if os.environ.get("LD_LIBRARY_PATH"):
        env["LD_LIBRARY_PATH"] = os.environ["LD_LIBRARY_PATH"]
    for key, var in (("cc", "CC"), ("cxx", "CXX")):
        if (engine or {}).get(key):
            env[var] = str((engine or {})[key])
    return env


@dataclass(frozen=True)
class Spawn:
    python: str
    args: tuple[str, ...]          # worker arguments after --fd/--parent (ends with "--", engine args)
    env: dict[str, str]
    pidfile: Path
    script: Path = WORKER
    passthrough: bool = False      # Diagnostics: worker output goes to the controller's stderr


def make_spawn(engine: Mapping[str, Any], data_dir: Path, state: Path, gpu_id: str, visible_gpu: str,
               passthrough: bool) -> Spawn:
    """How to start the worker for one GPU, from the `engine` settings."""
    return Spawn(python=str(engine.get("python") or ""), args=worker_args(engine, state),
                 env=worker_env(data_dir / "engine-home", visible_gpu, engine),
                 pidfile=data_dir / "run" / f"worker-{gpu_id}.pid", passthrough=passthrough)


def job_profile(engine: Mapping[str, Any], kind: str | None) -> Any:
    """The memory profile for a job on a model of this catalog `kind`: `profile_video` for a video model unless it
    follows `profile` (SAME); else `profile`."""
    video = engine.get("profile_video", SAME)
    return video if kind == "video" and video != SAME else engine.get("profile", ENGINE_OWN)


def worker_args(engine: Mapping[str, Any], state: Path, profile: Any = None) -> tuple[str, ...]:
    """The worker's arguments; `--profile` only when a memory profile is set (else the engine's own).
    `profile`: the one to use instead of the engine's `profile` (see `job_profile`)."""
    folders = [x for f in engine.get("model_folders", []) + engine.get("helper_folders", []) for x in ("--models", f)]
    profile = engine.get("profile", ENGINE_OWN) if profile is None else profile
    chosen = () if profile == ENGINE_OWN else ("--profile", f"{profile:g}")
    return ("--root", str(engine.get("root") or ""), "--state", str(state), *folders, *chosen, "--",
            *engine.get("args", []))


def _start_time(pid: int) -> str | None:
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def kill_orphan(pidfile: Path, script: Path) -> None:
    """Kill a worker left behind by an earlier controller (same pid, start time and script)."""
    try:
        info = json.loads(pidfile.read_text())
        pid, start = int(info["pid"]), str(info["start"])
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
    except (OSError, ValueError, KeyError, TypeError):
        pidfile.unlink(missing_ok=True)
        return
    if _start_time(pid) == start and str(script).encode() in cmdline:
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)
        for _ in range(100):
            if _start_time(pid) != start:
                break
            time.sleep(0.02)
    pidfile.unlink(missing_ok=True)


def exit_text(code: int | None) -> str:
    if code is not None and code < 0:
        try:
            return f"Engine stopped unexpectedly (signal {signal.Signals(-code).name})"
        except ValueError:
            return f"Engine stopped unexpectedly (signal {-code})"
    return f"Engine stopped unexpectedly (exit code {code})"


class Supervisor:
    def __init__(self, spawn: Spawn, on_event: Callable[[dict[str, Any]], None], *,
                 ready_timeout: float = 600.0, stop_grace: float = 5.0, term_grace: float = 3.0) -> None:
        self.spawn, self.on_event = spawn, on_event
        self.ready_timeout, self.stop_grace, self.term_grace = ready_timeout, stop_grace, term_grace
        self.state = "none"                      # none | starting | ready | stopping | down
        self.down_text: str | None = None
        self.engine: dict[str, Any] = {}
        self.pid: int | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._ready: asyncio.Future[None] | None = None
        self._reader: asyncio.Task[None] | None = None
        self._watcher: asyncio.Task[None] | None = None
        self._crashes: list[float] = []

    def reset(self) -> None:
        """Clear `down` and the crash history (Start pressed)."""
        if self.state == "down":
            self.state, self.down_text = "none", None
        self._crashes.clear()

    async def start(self) -> None:
        """Start the worker if needed and wait until it is ready."""
        if self.state == "stopping" and self._watcher is not None:
            await asyncio.shield(self._watcher)
        if self.state == "ready":
            return
        if self.state == "down":
            raise EngineFailed("runtime", self.down_text or "The engine is stopped")
        if self.state != "starting":
            self.state = "starting"
            self._ready = asyncio.get_running_loop().create_future()
            await self._spawn()
        assert self._ready is not None
        await asyncio.shield(self._ready)

    async def _spawn(self) -> None:
        if self._crashes:
            delay = BACKOFF_S[min(len(self._crashes), len(BACKOFF_S)) - 1]
            await asyncio.sleep(max(0.0, self._crashes[-1] + delay - time.monotonic()))
        sp = self.spawn
        if "HOME" in sp.env:
            Path(sp.env["HOME"]).mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(kill_orphan, sp.pidfile, sp.script)
        scoped = await asyncio.to_thread(enginescope.available)      # its own cgroup: a memory kill spares the Hub
        if self.state != "starting":
            return
        parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        reader, writer = await asyncio.open_unix_connection(sock=parent, limit=protocol.MAX_LINE + 1)
        out = sys.stderr if sp.passthrough else asyncio.subprocess.DEVNULL
        argv, env = [sp.python, "-B", "-s", "-X", "utf8", str(sp.script), "--fd", str(child.fileno()),
                     "--parent", str(os.getpid()), *sp.args], sp.env
        if scoped:
            argv, env = enginescope.wrap(argv, env, sp.pidfile.stem.removeprefix("worker-"))
        self._scoped = scoped
        try:
            proc = await asyncio.create_subprocess_exec(*argv, env=env, pass_fds=(child.fileno(),),
                                                        stdin=asyncio.subprocess.DEVNULL, stdout=out, stderr=out,
                                                        start_new_session=True)
        except OSError as exc:
            writer.close()
            self._fail_start(f"The engine's Python could not run: {exc.strerror or exc}")
            return
        finally:
            child.close()
        self._proc, self.pid, self._writer = proc, proc.pid, writer
        self._reader = asyncio.create_task(self._read(reader))
        self._watcher = asyncio.create_task(self._watch(proc))
        self._write_pidfile()
        asyncio.get_running_loop().call_later(self.ready_timeout, self._start_timeout, proc)

    def _write_pidfile(self) -> None:
        path, start = self.spawn.pidfile, _start_time(self.pid or 0)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"pid": self.pid, "start": start}))
        os.replace(tmp, path)

    def _start_timeout(self, proc: asyncio.subprocess.Process) -> None:
        if proc is self._proc and self.state == "starting":
            self.down_text = "The engine took too long to start"
            with contextlib.suppress(ProcessLookupError):
                proc.kill()

    def _fail_start(self, text: str, state: str = "down") -> None:
        self.state, self.down_text = state, text if state == "down" else None
        if self._ready is not None and not self._ready.done():
            self._ready.set_exception(EngineFailed("runtime", text))
            self._ready.exception()

    async def _read(self, reader: asyncio.StreamReader) -> None:
        try:
            while line := await reader.readline():
                msg = protocol.decode(line)
                ev = msg.get("ev")
                if ev == "ready" and self.state == "starting" and msg.get("proto") != protocol.PROTO:
                    self.down_text = OTHER_PROTO.format(msg.get("proto"), protocol.PROTO)   # refused: it goes down
                    if self._proc is not None:
                        with contextlib.suppress(ProcessLookupError):
                            self._proc.kill()
                elif ev == "ready" and self.state == "starting":
                    self.engine = dict(msg.get("engine") or {})
                    self.state = "ready"
                    if self._ready is not None and not self._ready.done():
                        self._ready.set_result(None)
                elif ev == "fatal":
                    self.down_text = str(msg.get("text") or "The engine could not start")
                else:
                    self.on_event(msg)
        except (ValueError, protocol.ProtocolError, ConnectionError):
            if self._proc is not None:
                with contextlib.suppress(ProcessLookupError):
                    self._proc.kill()

    async def _watch(self, proc: asyncio.subprocess.Process) -> None:
        code = await proc.wait()
        if self._reader is not None:
            done, _ = await asyncio.wait([self._reader], timeout=2.0)
            if not done:
                self._reader.cancel()
        if self._writer is not None:
            self._writer.close()
        self._writer, self._proc, self.pid = None, None, None
        self.spawn.pidfile.unlink(missing_ok=True)
        if self.state == "stopping":
            self._fail_start("The engine was stopped", state="none")
            self.on_event({"ev": "exit", "text": "The engine was stopped", "crash": False})
            return
        if self.state == "starting":                     # a scope that did not hold: plain at the next start
            again = getattr(self, "_scoped", False) and not self.down_text and enginescope.give_up()
            self._fail_start(self.down_text or exit_text(code).replace("unexpectedly", "while starting"),
                             "none" if again else "down")
            return
        now = time.monotonic()
        self._crashes = [t for t in self._crashes if now - t < CRASH_WINDOW_S] + [now]
        text = exit_text(code)
        if len(self._crashes) >= MAX_CRASHES:
            self.state, self.down_text = "down", f"{text}; stopped after {MAX_CRASHES} crashes"
        else:
            self.state = "none"
        self.on_event({"ev": "exit", "text": text, "crash": True})

    async def send(self, message: dict[str, Any]) -> None:
        if self.state != "ready" or self._writer is None:
            raise EngineFailed("runtime", "The engine is not running")
        try:
            self._writer.write(protocol.encode(message))
            await self._writer.drain()
        except (ConnectionError, OSError):
            raise EngineFailed("runtime", "The engine is not running") from None

    async def stop(self) -> None:
        """Ask the worker to exit; then SIGTERM; then SIGKILL."""
        proc, watcher = self._proc, self._watcher
        if proc is None or watcher is None:
            if self.state == "starting":
                self._fail_start("The engine was stopped", state="none")
            return
        self.state = "stopping"
        if self._writer is not None:
            with contextlib.suppress(ConnectionError, OSError):
                self._writer.write(protocol.encode({"op": "stop"}))
                await self._writer.drain()
        for sig, wait in ((None, self.stop_grace), (signal.SIGTERM, self.term_grace), (signal.SIGKILL, None)):
            if sig is not None:
                with contextlib.suppress(ProcessLookupError):
                    proc.send_signal(sig)
            try:
                await asyncio.wait_for(asyncio.shield(watcher), wait)
                return
            except TimeoutError:
                continue
