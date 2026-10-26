"""JSON state documents: one writer, atomic writes (temp + fsync + os.replace), debounced."""
from __future__ import annotations

import asyncio
import copy
import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

DEBOUNCE_S = 0.3


def write_json(path: Path, value: Any, mode: int = 0o600) -> None:
    """Write `value` to `path` atomically. A crash leaves either the old or the new file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, indent=1, ensure_ascii=False).encode("utf-8")
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def read_json(path: Path) -> Any:
    """Read a JSON file; a missing file gives None. Bad JSON raises ValueError with a plain line."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"{path} is not valid JSON (line {e.lineno})") from None


class JsonDoc:
    """An in-memory dict mirrored to one file. Implements `api.JsonDoc`."""

    def __init__(self, path: Path, default: dict, mode: int = 0o600) -> None:
        self.path, self.mode = path, mode
        loaded = read_json(path)
        if loaded is not None and not isinstance(loaded, dict):
            raise ValueError(f"{path} must hold a JSON object")
        self._value: dict = loaded if loaded is not None else copy.deepcopy(default)
        self._timer: asyncio.TimerHandle | None = None
        self._version = 0
        self._saved = 0
        self._lock = threading.Lock()

    def get(self) -> dict:
        return copy.deepcopy(self._value)

    def patch(self, changes: dict) -> dict:
        self._value.update(copy.deepcopy(changes))
        self._schedule()
        return self.get()

    def replace(self, value: dict) -> None:
        self._value = copy.deepcopy(value)
        self._schedule()

    def _schedule(self) -> None:
        self._version += 1
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self.flush()
            return
        if self._timer is not None:
            self._timer.cancel()
        self._timer = loop.call_later(DEBOUNCE_S, self._write_later)

    def _write_later(self) -> None:
        self._timer = None
        snapshot, version = copy.deepcopy(self._value), self._version
        fut = asyncio.get_running_loop().run_in_executor(None, self._write, snapshot, version)
        fut.add_done_callback(self._report)

    def _write(self, value: dict, version: int) -> None:
        with self._lock:
            if version > self._saved:
                write_json(self.path, value, self.mode)
                self._saved = version

    def _report(self, fut: asyncio.Future[None]) -> None:
        if not fut.cancelled() and fut.exception() is not None:
            print(f"hub: could not save {self.path}: {fut.exception()}", file=sys.stderr)

    def flush(self) -> None:
        """Write now if anything is unsaved (used at shutdown)."""
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        self._write(self._value, self._version)


class Store:
    """Owns every open JsonDoc so shutdown can flush them all."""

    def __init__(self) -> None:
        self._docs: dict[Path, JsonDoc] = {}

    def doc(self, path: Path, default: dict, mode: int = 0o600) -> JsonDoc:
        if path not in self._docs:
            self._docs[path] = JsonDoc(path, default, mode)
        return self._docs[path]

    def flush(self) -> None:
        for doc in self._docs.values():
            doc.flush()
