"""Tensor names from safetensors headers (8-byte little-endian length + JSON; nothing past the header is read),
remembered per file in <data>/engine/fingerprints.json while size and mtime are unchanged; plus the small JSON
read/write the registry uses.
"""
from __future__ import annotations

import json
import os
import struct
import tempfile
from pathlib import Path
from typing import Any

MAX_HEADER = 100 * 1024 * 1024        # the safetensors format's own header limit


def tensor_names(path: str) -> frozenset[str] | None:
    """The tensor names in a safetensors header, or None when the file is not one."""
    try:
        with open(path, "rb") as f:
            head = f.read(8)
            if len(head) != 8:
                return None
            size = struct.unpack("<Q", head)[0]
            if not 2 <= size <= MAX_HEADER:
                return None
            header = json.loads(f.read(size))
    except (OSError, ValueError):
        return None
    return frozenset(k for k in header if k != "__metadata__") if isinstance(header, dict) else None


class Fingerprints:
    """Tensor names per file, kept in <data>/engine/fingerprints.json under the path, valid while size and
    mtime are unchanged."""

    def __init__(self, path: Path) -> None:
        self.path, self.used, self.dirty = path, set(), False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        self.data: dict[str, Any] = data if isinstance(data, dict) else {}

    def get(self, path: str) -> tuple[frozenset[str] | None, int]:
        try:
            st = os.stat(path)
        except OSError:
            return None, 0
        self.used.add(path)
        entry = self.data.get(path)
        if isinstance(entry, dict) and entry.get("size") == st.st_size and entry.get("mtime_ns") == st.st_mtime_ns:
            return frozenset(entry.get("tensors") or ()), st.st_size
        names = tensor_names(path)
        self.data[path] = {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "tensors": sorted(names or ())}
        self.dirty = True
        return names, st.st_size

    def save(self) -> None:
        for gone in set(self.data) - self.used:
            del self.data[gone]
            self.dirty = True
        if self.dirty:
            write_json(self.path, self.data)


def write_json(path: Path, value: Any) -> None:
    """Whole or not at all; two writers never share a temp file. Mode 0644 (rw-r--r--)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(value, indent=1))
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def read_json(path: str | Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


