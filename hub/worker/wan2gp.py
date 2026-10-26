"""The session loop over Wan2GP's in-process API (`shared.api`), shared by both Wan2GP adapters. The worker never
writes the engine root: config, per-model settings and outputs live in `state` (hub data). The only hub files in the
root are the controller's pointer definitions in `finetunes/` (hub_auto), read like any finetune at start. Private
engine attributes used here are marked as such. What differs between the engine lines (how a task is filled, factory
settings, LoRA folders, key families) is the adapter's (`adapters/`, picked by `select` once the session is open): no
engine line is named here. A task arrives as the Hub's request (`enginerequests`); the adapter turns it into the
engine's task (`Adapter.task`) and fills it (`Adapter.translate`); `plan` asks the engine what it would make of it.
Events go back in the Hub's words (`protocol`)."""
from __future__ import annotations

import contextlib
import functools
import importlib
import os
import shutil
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

try:
    from . import adapters, catalog, definitions, faults, keep
    from .wgpconfig import FORCED_CONFIG, own_tmp, search_paths, seed_config
except ImportError:  # run as a script by the engine's Python
    import adapters
    import catalog
    import definitions
    import faults
    import keep
    from wgpconfig import FORCED_CONFIG, own_tmp, search_paths, seed_config

__all__ = ["FORCED_CONFIG", "Engine", "search_paths", "seed_config"]

MB = 1024 * 1024
Emit = Callable[[dict[str, Any]], None]

QUEUE_FILES = ("queue.zip", "error_queue.zip")
# What this module reads from the engine (R9 §3; the contract test), each tagged with the line that publishes it.
READS: dict[str, dict[str, str]] = {
    "wgp": {"WanGP_version": "both", "settings_version": "both", "server_config": "both", "get_lora_dir": "both",
            "wan_model": "both", "transformer_type": "both", "_get_dropdown_deps": "both"},
    "api": {"init": "both", "submit_task": "both", "events": "both", "iter": "both", "kind": "both", "data": "both",
            "phase": "both", "current_step": "both", "total_steps": "both", "progress": "both", "status": "both",
            "result": "both", "cancel_requested": "both", "cancel": "both", "_thread": "both",
            "generated_files": "both", "errors": "both"},
    "definition": {},
    "settings": {},
    "generate_video": {},
    "suffixes": {},
}


def rss_mb(key: str = "VmRSS:") -> int | None:
    """This process's resident memory in MB (`VmHWM:`: its high-water mark since it started)."""
    try:
        with open("/proc/self/status", encoding="ascii") as f:
            for line in f:
                if line.startswith(key):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


class Peaks:
    """Peak GPU memory in use on the device (whole card, like NVML) and this process's RSS during one task.
    Sampled at each event; the allocator's own peak covers the gaps."""

    def __init__(self) -> None:
        self.cuda = getattr(sys.modules.get("torch"), "cuda", None)
        self.vram: int | None = None
        self.rss: int | None = None
        self._call("reset_peak_memory_stats")
        self._start = self._used()
        self._reserved = self._call("memory_reserved")

    def _call(self, name: str) -> int | None:
        try:
            return int(getattr(self.cuda, name)()) // MB
        except Exception:
            return None

    def _used(self) -> int | None:
        try:
            free, total = self.cuda.mem_get_info()
        except Exception:
            return None
        return int(total - free) // MB

    def sample(self, final: bool = False, mark: bool = False) -> None:
        """`mark` (a clip's final sample): the RSS peak is the process's own high-water mark, which a fresh worker's
        one clip makes its true peak."""
        values = [self._used()]
        top = self._call("max_memory_reserved") if final else None
        if final and None not in (self._start, self._reserved, top):
            values.append(self._start + top - self._reserved)
        self.vram = max([self.vram or 0, *(v for v in values if v is not None)]) or self.vram
        seen = [r for r in (rss_mb(), rss_mb("VmHWM:") if mark else None) if r is not None]
        self.rss = max([self.rss or 0, *seen]) if seen else self.rss


class Engine:
    def __init__(self, root: str, state: str, args: list[str], model_folders: list[str],
                 profile: float | None = None) -> None:
        self.root = os.path.abspath(root)
        self.state = os.path.abspath(state)
        self.args = list(args)
        self.model_folders = list(model_folders)
        self.profile = profile                        # the memory profile set; None: the engine config's own
        self.api = "legacy"
        self.adapter: Any = None                      # the engine line's (`adapters.select`), once open
        self.session: Any = None
        self.w: Any = None
        self._lock = threading.Lock()
        self._job: Any = None
        self._job_id: str | None = None
        self._cancel_pending: str | None = None
        self._factory: dict[str, dict] = {}
        self._entries: dict[str, dict] = {}           # catalog entries read for tasks, once per worker
        self.made = 0                                 # the files the engine returned for the last task
        self.sent: dict[str, Any] = {}                # the last engine task submitted, as sent (`adapter.window`)

    def open(self) -> dict[str, Any]:
        """Start the engine. The cwd stays the engine root, as the engine expects. The outbox, the engine's settings
        folder and its temp folder (`own_tmp`) start empty: whatever a crash left there is gone. What the engine
        would fetch at start is found first (`adapters.prepare`: one line when not here). While it imports, every
        weight file in the model folders, the root's `ckpts` and the config's checkpoint folders is held (`keep`):
        its start never erases one."""
        os.chdir(self.root)
        adapters.prepare(self.root)
        outbox, settings_dir = os.path.join(self.state, "outbox"), os.path.join(self.state, "settings")
        for d in (outbox, settings_dir, *own_tmp()):     # the engine's temps too (TMPDIR in data/)
            shutil.rmtree(d, ignore_errors=True)
            os.makedirs(d, exist_ok=True)
        for name in QUEUE_FILES:                      # a queue an older engine run wrote out: gone
            for folder in (self.root, os.path.join(self.state, "config")):
                with contextlib.suppress(OSError):
                    os.unlink(os.path.join(folder, name))
        config = seed_config(self.root, os.path.join(self.state, "config"), outbox, self.model_folders, self.profile,
                             adapters.forced_config(self.root))
        if self.root not in sys.path:
            sys.path.insert(0, self.root)
        keep.hold([*self.model_folders, os.path.join(self.root, "ckpts"), *keep.config_roots(self.root, config)])
        try:
            api = importlib.import_module("shared.api")
            self.session = api.init(root=self.root, config_path=config, output_dir=outbox,
                                    cli_args=[*self.args, "--settings", settings_dir], console_output=False)
        finally:
            keep.release()
        self.w = sys.modules["wgp"]
        self.adapter = adapters.select(self.root, self.session)
        self.adapter.opened(self.w)
        self.w.get_lora_dir = functools.partial(catalog.lora_dir, self.w, self.root,  # never creates folders
                                                adapter=self.adapter)
        self.api = self.adapter.flavour
        self.w.server_config.update({**FORCED_CONFIG, **self.adapter.forced_config})
        return {"api": self.api, "version": str(self.w.WanGP_version), "settings_version": self.w.settings_version}

    def loaded(self) -> str | None:
        """The model held by the engine (private globals `wan_model`, `transformer_type`)."""
        return self.w.transformer_type if getattr(self.w, "wan_model", None) is not None else None

    def catalog(self) -> dict[str, Any]:
        """The catalog plus `weights`: the facts the controller matches new weight files against (left out, never
        the catalog, if the engine cannot answer them)."""
        data = catalog.build(self.w, self.root, self.adapter)
        try:
            image_types = [m["id"] for m in data["models"] if m["kind"] == "image"]
            data["weights"] = definitions.weights(self.w, self.w._get_dropdown_deps(), self.root, image_types)
        except Exception:
            pass
        return data

    def entry(self, model: str) -> dict[str, Any]:
        """The model's catalog entry, as the adapter's rules read it (once per worker): what its task is built from."""
        if model not in self._entries:
            found = catalog.entry(self.w, self.root, self.adapter, model)
            if found is None:
                raise LookupError(f"The engine has no model {model}")
            self._entries[model] = found
        return self._entries[model]

    def _task(self, request: Any) -> dict:
        """The engine task a Hub request becomes (`adapter.task`)."""
        return self.adapter.task(request, self.entry(request.model))

    def _params(self, task: dict, model: str) -> dict:
        """The task as this engine line takes it (`adapter.translate`), its factory settings underneath if wanted."""
        if self.adapter.factory_underneath and model not in self._factory:
            self._factory[model] = self.adapter.factory_settings(self.w, model)
        return self.adapter.translate(task, self._factory.get(model, {}))

    def lacking(self, model_type: str | None, strict: bool = False) -> list[str]:
        """The files the engine would fetch before the model loads (`adapter.lacking`); an engine that cannot tell
        refuses nothing unless `strict`."""
        try:
            return list(self.adapter.lacking(self.w, model_type))
        except Exception:
            if strict:
                raise
            return []

    def missing_weights(self, model: str | None = None) -> list[str]:
        """One line per file the engine would fetch: those every model needs, then each one's own (for `model`,
        else every model whose main file is here), with the models that need it."""
        shared = self.lacking(None, strict=True)
        models = [model] if model else [m["id"] for m in catalog.build(self.w, self.root, self.adapter)["models"]
                                        if m["status"] != "missing"]
        need: dict[str, list[str]] = {}
        for m in models:
            for key in self.lacking(m, strict=True):
                if key not in shared:
                    need.setdefault(key, []).append(m)
        return [f"{k} (every model)" for k in shared] + [f"{k} ({', '.join(v)})" for k, v in need.items()]

    def model_files(self, models: list[str]) -> dict[str, list[dict[str, Any]]]:
        """For each model, its parts that name a file and where each is now (`adapters/modelfiles.py`)."""
        return {str(m): list(self.adapter.modelfiles.parts(self.w, str(m))) for m in models}

    def plan(self, request: Any) -> dict[str, Any]:
        """What the engine would make of a request, by its own preflight (`adapters/plan.py`): no GPU work."""
        return self.adapter.plan(self.session, self._params(self._task(request), request.model))

    def cancel(self, job_id: str) -> None:
        with self._lock:
            if self._job_id == job_id and self._job is not None:
                self._job.cancel()
            else:
                self._cancel_pending = job_id

    def run(self, job_id: str, task: int, request: Any, emit: Emit) -> dict[str, Any]:
        """Run one task (`request`, the Hub's picture, clip or line request) to completion (blocking); reports through
        `emit` and returns `task_done`."""
        started, self.sent = time.monotonic(), {}
        base = {"job": job_id, "task": task}
        model, clip = request.model, request.kind == "video"
        loading = model != self.loaded()
        lack = self.lacking(model) if loading else []  # refused before the engine runs (and would try to fetch it)
        if lack:
            self.made = 0
            return {**base, "ev": "task_done", "ok": False, "model": self.loaded(), "error": {
                "stage": "runtime", "text": f"The engine lacks a companion file: {os.path.basename(lack[0])}"}}
        if loading:
            emit({"ev": "model", "state": "loading", "model": model, "rss_mb": rss_mb()})
        peaks = Peaks()
        errors: list[Any] = []
        result, cancelled = None, False
        try:
            params = self.sent = self._params(self._task(request), model)
            with self._lock:
                cancelled = self._cancel_pending == job_id
                self._cancel_pending = None
                job = None if cancelled else self.session.submit_task(params)
                self._job, self._job_id = job, job_id
            if job is not None:
                for event in job.events.iter(timeout=0.5):
                    if event.kind == "error":
                        errors.append(event.data)
                    elif event.kind == "progress":
                        p = event.data
                        peaks.sample()
                        if loading and p.phase != "loading_model":
                            loading = False
                            emit({"ev": "model", "state": "loaded", "model": model, "rss_mb": rss_mb()})
                        emit({**base, "ev": "progress", "phase": p.phase, "step": p.current_step,
                              "steps": p.total_steps, "pct": p.progress, "text": p.status})
                result = job.result()
                cancelled = bool(job.cancel_requested)
                runner = getattr(job, "_thread", None)  # private: the engine resets its state after the result
                if runner is not None:
                    runner.join(30)
        except Exception as exc:
            errors.append(exc)
        finally:
            with self._lock:
                self._job, self._job_id = None, None
        peaks.sample(final=True, mark=clip)
        files = list(getattr(result, "generated_files", None) or [])
        self.made = len(files)
        if clip and len(files) > 1:                   # chained passes: each file holds the ones before; keep the last
            for path in files[:-1]:
                with contextlib.suppress(OSError):
                    os.unlink(path)
            files = files[-1:]
        if files and getattr(request, "judge", None):    # the judges run next: say so, not 100 %
            emit({**base, "ev": "progress", "phase": "checking", "pct": 100.0, "text": "Checking the take…"})
        verdict = self.adapter.finish(request, self.sent, files)   # a line's joins and judge
        if loading and self.loaded() == model:
            emit({"ev": "model", "state": "loaded", "model": model, "rss_mb": rss_mb()})
        for path in files:
            emit({**base, "ev": "output", "file": os.path.abspath(path)})
        errors.extend(getattr(result, "errors", None) or [])
        ok = bool(files) and not errors and not cancelled
        done = {**base, "ev": "task_done", "ok": ok, "seconds": round(time.monotonic() - started, 2),
                "model": self.loaded(), "peak_vram_mb": peaks.vram, "peak_rss_mb": peaks.rss,
                **({"judge": verdict} if isinstance(verdict, dict) else {})}
        if not ok:
            done["error"] = faults.failure(errors, cancelled)
        return done
