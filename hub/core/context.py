"""What a module sees: `Ctx` (api.py) implemented over the core services.

The Network and Assistant cards also use two core-owned admin surfaces carried on the
same object, `ctx.network` and `ctx.mcp`; other modules never need them.
"""
from __future__ import annotations

import asyncio
import copy
import re
import sys
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

from hub.core.api import Invalid, Job
from hub.core.bus import Bus
from hub.core.jobs import JobBook
from hub.core.store import JsonDoc, Store

_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")
NOT_RUNNING = "The assistant is not running"   # a service nobody offers: its module is gone or not started


class Events:
    """Internal core events delivered to module `listens` (never to screens)."""

    def __init__(self) -> None:
        self.listeners: dict[str, list[tuple[Callable[..., Awaitable[None]], Any]]] = {}
        self._tasks: set[asyncio.Task] = set()

    def listen(self, event: str, fn: Callable[..., Awaitable[None]], ctx: Any) -> None:
        self.listeners.setdefault(event, []).append((fn, ctx))

    def emit(self, event: str, data: dict) -> None:
        for fn, ctx in self.listeners.get(event, []):
            task = asyncio.get_running_loop().create_task(self._call(fn, ctx, copy.deepcopy(data)))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    @staticmethod
    async def _call(fn: Callable[..., Awaitable[None]], ctx: Any, data: dict) -> None:
        """One listener; its refusal or fault is one line on stderr (never silent), the others still run."""
        try:
            await fn(ctx, data)
        except Exception as exc:  # noqa: BLE001
            first = (str(exc).strip().splitlines() or [""])[0] or type(exc).__name__
            print(f"{getattr(ctx, 'module_id', '?')} listener {fn.__name__}: {first}", file=sys.stderr)


class NoEngine:
    """Stands in when no engine GPU is configured."""

    async def query(self, what: str, **args: Any) -> dict:
        raise RuntimeError("No engine is set up on this server")


class ModuleBus:
    """Publishes on the module's own lanes; lanes and types are prefixed `<id>.`."""

    def __init__(self, bus: Bus, module_id: str) -> None:
        self._bus, self._id = bus, module_id

    def _prefixed(self, name: str) -> str:
        return name if name.startswith(self._id + ".") else f"{self._id}.{name}"

    def publish(self, lane: str, type: str, data: dict, key: str | None = None) -> None:
        self._bus.publish(self._prefixed(lane), self._prefixed(type), data, key)

    def presence(self) -> dict:
        return self._bus.presence()


class ModuleJobs:
    """`api.Jobs` for one module: a bare kind ("image") means this module's kind; its jobs are `by` this module."""

    def __init__(self, book: JobBook, module_id: str) -> None:
        self._book, self._id = book, module_id

    def submit(self, kind: str, params: dict) -> Job:
        return self._book.submit(kind if "." in kind else f"{self._id}.{kind}", params, by=self._id)

    def get(self, job_id: str) -> Job | None:
        return self._book.get(job_id)

    def cancel(self, job_id: str) -> Job | None:
        return self._book.cancel(job_id)

    def note(self, job_id: str, **values: Any) -> Job | None:
        return self._book.note(job_id, **values)

    def card(self, job_id: str) -> dict | None:
        """The job's card as the queue shows it: `position`, `progress` (the takes line)."""
        return self._book.card(job_id)

    def refuse(self, job_id: str, text: str) -> Job | None:
        return self._book.refuse(job_id, text)


class ModuleCtx:
    def __init__(self, core: Any, module_id: str, data_dir: Path, settings: Mapping[str, Any], store: Store) -> None:
        self._core, self._store = core, store
        self.module_id = module_id
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings: Mapping[str, Any] = MappingProxyType(copy.deepcopy(dict(settings)))
        self.files = core.files
        self.bus = ModuleBus(core.bus, module_id)
        self.jobs = ModuleJobs(core.book, module_id)
        self.network = core.network
        self.mcp = core.mcp

    @property
    def engine(self) -> Any:
        return self._core.engine

    def doc(self, name: str, default: dict) -> JsonDoc:
        if not _NAME.match(name):
            raise ValueError(f"Bad document name {name!r}")
        return self._store.doc(self.data_dir / f"{name}.json", default)

    def emit(self, event: str, data: dict) -> None:
        self._core.events.emit(event, data)

    def offer(self, name: str, fn: Callable[..., Any]) -> None:
        """A service other modules use by name (`service`), without importing this one."""
        self._core.services[name] = fn

    def service(self, name: str) -> Callable[..., Any]:
        found = self._core.services.get(name)
        if found is None:
            raise Invalid("assistant", NOT_RUNNING)
        return found
