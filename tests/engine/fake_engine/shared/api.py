"""Fake `shared.api` for both engine flavours: the session surface the hub worker uses.

Event semantics follow the real API: a job's `events.iter()` yields progress/error/
completed events and ends when the job closes; `cancel()` is cooperative.
"""
from __future__ import annotations

import contextlib
import importlib
import os
import queue
import sys
import threading
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProgressUpdate:
    phase: str
    status: str
    progress: int
    current_step: int | None
    total_steps: int | None


@dataclass(frozen=True)
class SessionEvent:
    kind: str
    data: Any = None
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class GenerationError:
    message: str
    task_index: int | None = None
    task_id: Any = None
    stage: str | None = None


@dataclass(frozen=True)
class GenerationResult:
    success: bool
    generated_files: list[str]
    errors: list[GenerationError]
    total_tasks: int
    successful_tasks: int
    failed_tasks: int


class SessionStream:
    def __init__(self) -> None:
        self._queue: queue.Queue[SessionEvent | None] = queue.Queue()
        self._closed = threading.Event()

    def put(self, kind: str, data: Any = None) -> None:
        if not self._closed.is_set():
            self._queue.put(SessionEvent(kind, data))

    def close(self) -> None:
        self._closed.set()
        self._queue.put(None)

    def iter(self, timeout: float | None = None) -> Iterator[SessionEvent]:
        while True:
            try:
                event = self._queue.get(timeout=timeout)
            except queue.Empty:
                continue
            if event is None:
                return
            yield event


class SessionJob:
    def __init__(self) -> None:
        self.events = SessionStream()
        self._done = threading.Event()
        self._cancel = threading.Event()
        self._result: GenerationResult | None = None

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancel_requested(self) -> bool:
        return self._cancel.is_set()

    def result(self, timeout: float | None = None) -> GenerationResult:
        self._done.wait(timeout)
        assert self._result is not None
        return self._result


@contextlib.contextmanager
def _pushd(path: str) -> Iterator[None]:
    previous = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _phase(status: str) -> str:
    return "loading_model" if status.lower().startswith("loading") else "inference"


class WanGPSession:
    def __init__(self, root: str, config_path: str | None, output_dir: str | None, cli_args: Sequence[str]) -> None:
        self._root = os.path.abspath(root)
        self._config_path = config_path
        self._output_dir = output_dir
        self._cli_args = list(cli_args)
        self._state: dict[str, Any] = {"gen": {"file_list": [], "file_settings_list": []}}
        self._active: SessionJob | None = None

    def ensure_ready(self) -> WanGPSession:
        argv = ["wgp.py", *self._cli_args]
        if self._config_path:
            argv += ["--config", os.path.dirname(os.path.abspath(self._config_path))]
        if self._root not in sys.path:
            sys.path.insert(0, self._root)
        saved, sys.argv = sys.argv, argv
        try:
            with _pushd(self._root):
                wgp = importlib.import_module("wgp")
        finally:
            sys.argv = saved
        if wgp.FLAVOUR == "upstream":
            self.list_model_defs = lambda **_: [dict(md, model_type=mt) for mt, md in wgp.models_def.items()]
        return self

    def submit_task(self, settings: dict[str, Any]) -> SessionJob:
        if self._active is not None and not self._active._done.is_set():
            raise RuntimeError("WanGP session already has a generation in progress")
        job = self._active = SessionJob()
        task = {"id": 1, "params": dict(settings), "prompt": settings.get("prompt", "")}
        threading.Thread(target=self._run, args=(job, task), daemon=True).start()
        return job

    def _run(self, job: SessionJob, task: dict[str, Any]) -> None:
        wgp = sys.modules["wgp"]
        errors: list[GenerationError] = []
        made: list[dict] = []
        outdir = self._output_dir or os.path.join(self._root, "outputs")
        wgp.server_config["save_path"] = wgp.server_config["image_save_path"] = outdir

        def send(command: str, data: Any) -> None:
            (current, total), status = data
            progress = int(current / total * 100)
            job.events.put("progress", ProgressUpdate(_phase(status), status, progress, current, total))

        try:
            with _pushd(self._root):
                made = wgp.generate(wgp.validate_task(task), send, job._cancel.is_set, outdir)
        except Exception as exc:
            errors.append(GenerationError(str(exc), 1, 1, "generation"))
            job.events.put("error", errors[-1])
        if job.cancel_requested:
            errors.append(GenerationError("Generation was cancelled", 1, 1, "cancelled"))
            job.events.put("error", errors[-1])
        self._state["gen"]["file_list"] += [m["path"] for m in made]
        self._state["gen"]["file_settings_list"] += [m["settings"] for m in made]
        files = [m["path"] for m in made]
        job._result = GenerationResult(not errors, files, errors, 1, int(not errors), int(bool(errors)))
        job.events.put("completed", job._result)
        job._done.set()
        job.events.close()

    def close(self) -> None:
        sys.modules["wgp"].release_model()


def init(*, root: str, config_path: str | None = None, output_dir: str | None = None,
         callbacks: object | None = None, cli_args: Sequence[str] = (), console_output: bool = True) -> WanGPSession:
    return WanGPSession(root, config_path, output_dir, cli_args).ensure_ready()
