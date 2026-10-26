"""The engine lane's catalog: `query` (api.Engine) answered from memory, the cache file or the worker, one fetch at a
time; new weight files are matched (`autoreg`) and the engine re-read when a definition was written. `files`: each
model's parts that name a file, and the file chosen for one (`adapters/modelfiles.py`).

A mixin of `engine.EngineLane`, which holds the state named below."""
from __future__ import annotations

import asyncio
import itertools
from pathlib import Path
from typing import Any

from hub.core import autoreg, enginecat
from hub.core.enginecat import catalog_key
from hub.core.supervisor import EngineFailed, Supervisor
from hub.worker import adapters


class CatalogQueries:
    sup: Supervisor
    cache: Path
    catalog_key: str
    engine: dict[str, Any] | None
    lora_roots: list[str]
    _catalog: dict[str, Any] | None
    _found: autoreg.Found | None
    _files: tuple[str, dict[str, Any]] | None
    _model: str | None
    _queries: dict[str, asyncio.Future[dict[str, Any]]]
    _ids: itertools.count
    _lock: asyncio.Lock
    _fetching: asyncio.Lock
    _fetches: int
    _fresh: int

    def _set_model(self, model: Any) -> None:
        raise NotImplementedError

    # ---------------------------------------------------------------- api.Engine
    def cached_catalog(self) -> dict[str, Any] | None:
        """The catalog as last read: in memory, else the cache file (None: neither has it). Never asks the worker."""
        if self._catalog is None:
            self._catalog = enginecat.read_cache(self.cache, self.catalog_key)
        return self._catalog

    async def query(self, what: str, **args: Any) -> dict:
        """`models` (`rescan=True`: look at the folders again): the catalog plus the resident model. `weights`
        (`rescan`; `choose=(path, base)`: save the chosen base, then rescan): the Image models panel (autoreg)."""
        if what == "weights":
            if args.get("choose") is not None:
                await asyncio.to_thread(autoreg.choose, self.cache.parent, *args["choose"])
            again = bool(args.get("rescan")) or args.get("choose") is not None or self._found is None
            return autoreg.panel(await self.query("models", rescan=again), self._found)
        if what == "files":
            return await self._model_files(args.get("choose"), bool(args.get("rescan")))
        if what in ("plan", "voice"):          # the plan of a request; SeedVC on, what it lacks
            await self.sup.start()
            return (await self._ask(what, **({"request": args.get("request")} if what == "plan" else {}))) or {}
        if what != "models":
            raise ValueError(f"Unknown engine question: {what}")
        asked = self._fetches                  # a rescan is answered by a fetch that starts after this
        if self.engine is not None:
            key = await asyncio.to_thread(catalog_key, self.engine)
            if key != self.catalog_key:
                self.catalog_key, self._catalog = key, None
        if args.get("rescan"):
            self._catalog = None
        elif self._catalog is None:
            self._catalog = await asyncio.to_thread(enginecat.read_cache, self.cache, self.catalog_key)
        if self._catalog is None:
            await self._load(asked if args.get("rescan") else None)
        if self._catalog is None:
            raise EngineFailed("runtime", "The engine did not list its models")
        models = [enginecat.with_lora_roots(m, self.lora_roots) for m in self._catalog["models"]]
        return {**self._catalog, "models": models, "resident": self._model}

    async def _load(self, asked: int | None) -> None:
        """Single flight: one fetch at a time, so no query stops a worker another query (or a re-read) still asks.
        A query that waited takes what the fetch before it got; a rescan only a fetch started after `asked`."""
        async with self._fetching:
            if self._catalog is not None and (asked is None or self._fresh > asked):
                return
            started = self.sup.state != "ready"
            try:
                await self.sup.start()
                await self._fetch_catalog()
            finally:
                if started and self._model is None and not self._lock.locked():
                    async with self._lock:
                        await self.sup.stop()

    async def _fetch_catalog(self) -> None:
        """Ask the worker for its catalog (callers hold `_fetching`); new weight files are matched first (`autoreg`).
        When a pointer definition was written or removed, the catalog comes from a worker started after that."""
        number = self._fetches = self._fetches + 1
        reply = await self._ask_catalog()
        found = await asyncio.to_thread(autoreg.refresh, reply, self.engine, self.lora_roots, self.cache.parent)
        if found.changed:
            reply = await self._reread()
            if self.engine is not None:        # the definition folder changed: so did the catalog's key
                self.catalog_key = await asyncio.to_thread(catalog_key, self.engine)
        if reply:
            self._found, self._catalog, self._fresh = found, reply, number
            await asyncio.to_thread(enginecat.write_cache, self.cache, self.catalog_key, self._catalog)

    async def _reread(self) -> dict[str, Any] | None:
        """The engine reads definitions only when it starts: once no job runs, start it again, ask, then stop it."""
        async with self._lock:
            await self.sup.stop()
            self._set_model(None)
            try:
                await self.sup.start()
                return await self._ask_catalog()
            except EngineFailed:
                return None
            finally:
                await self.sup.stop()

    async def _ask_catalog(self) -> dict[str, Any] | None:
        qid = f"q{next(self._ids)}"
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._queries[qid] = fut
        try:
            await self.sup.send({"op": "query", "id": qid, "what": "catalog"})
            reply = await fut
        except EngineFailed:
            self._queries.pop(qid, None)
            return None
        return reply["data"] if isinstance(reply.get("data"), dict) else None

    async def _model_files(self, choose: tuple[str, str, str | None] | None, rescan: bool = False) -> dict:
        """{model id: its parts that name a file} for every model in the catalog, kept while the catalog is the
        same (`rescan`: ask again). `choose=(model, part, path)` writes that choice first (path None: the
        engine's own) once no job runs; the engine reads its definitions again when it next starts."""
        if choose is not None:
            async with self._lock:
                try:
                    await self._choose_file(*choose)
                finally:
                    self._set_model(None)
                    await self.sup.stop()
            self._files = None
        cat = await self.query("models", rescan=choose is not None)
        ids = [m["id"] for m in cat["models"]]
        async with self._fetching:
            if not rescan and self._files is not None and self._files[0] == self.catalog_key:
                return self._files[1]
            started = self.sup.state != "ready"
            try:
                await self.sup.start()
                found = await self._ask("files", models=ids)       # answered beside a running job
            finally:
                if started and self._model is None and not self._lock.locked():
                    async with self._lock:
                        await self.sup.stop()
            if not isinstance(found, dict) or not isinstance(found.get("models"), dict):
                raise EngineFailed("runtime", "The engine did not list its models' files")
            self._files = (self.catalog_key, found["models"])
            return found["models"]

    async def _choose_file(self, model: str, part: str, path: str | None) -> None:
        """The chosen file `path` for one part of `model`, written where the engine reads definitions: the part as the
        listing gave it while the catalog is the same, else as the worker gives it now."""
        root = str((self.engine or {}).get("root") or "")
        if not root:
            raise ValueError("The engine's folder is not set")
        listed = self._files[1] if self._files is not None and self._files[0] == self.catalog_key else None
        if listed is None or model not in listed:
            await self.sup.start()
            listed = ((await self._ask("files", models=[model])) or {}).get("models") or {}
        record = next((p for p in listed.get(model) or [] if p.get("part") == part), None)
        if record is None:
            raise ValueError(f"{model} has no part {part}")
        await asyncio.to_thread(adapters.select(root).modelfiles.choose, root, model, record, path)

    async def _ask(self, what: str, **extra: Any) -> dict[str, Any] | None:
        """One question to the running worker; its error line raises."""
        qid = f"q{next(self._ids)}"
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._queries[qid] = fut
        try:
            await self.sup.send({"op": "query", "id": qid, "what": what, **extra})
            reply = await fut
        except EngineFailed:
            self._queries.pop(qid, None)
            raise
        if reply.get("error"):
            raise EngineFailed("runtime", str(reply["error"]))
        return reply["data"] if isinstance(reply.get("data"), dict) else None
