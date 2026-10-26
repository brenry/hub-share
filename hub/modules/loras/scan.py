"""LoRA folders as the engine sees them: one family folder per model, recursive or flat (the engine's way).

Ids are `<family folder name>/<path inside it>`. Nothing outside the folder is listed:
file symlinks must point inside it and folder symlinks are never followed. Read-only.
"""
from __future__ import annotations

import os
import posixpath
import re
from dataclasses import dataclass
from typing import Any

from . import header

EXTS = (".safetensors", ".sft")
SIDECARS = (".preview.png", ".preview.webp", ".preview.jpg", ".preview.jpeg",
            ".png", ".webp", ".jpg", ".jpeg", ".gif")
MAX_DEPTH, MAX_FILES = 8, 5000
OTHER = "Other"


@dataclass(frozen=True)
class Family:
    key: str
    dirs: tuple[str, ...]
    recursive: bool


@dataclass(frozen=True)
class Entry:
    id: str
    rel: str
    path: str
    size: int
    mtime: int
    mtime_ns: int
    sidecar: str | None

    @property
    def group(self) -> str:
        return self.rel.split("/", 1)[0] if "/" in self.rel else OTHER

    @property
    def stem(self) -> str:
        return os.path.splitext(posixpath.basename(self.rel))[0]


def families(cat: dict[str, Any]) -> dict[str, Family]:
    """One family per engine LoRA folder; the LoRA folders in Settings (`lora_extra`) come after it."""
    out: dict[str, Family] = {}
    for m in cat.get("models", []):
        if m.get("loras") and m.get("lora_dirs"):
            dirs = tuple(dict.fromkeys([*m["lora_dirs"], *(m.get("lora_extra") or [])]))
            fam = Family(os.path.basename(m["lora_dirs"][0]), dirs, bool(m.get("lora_recursive")))
            out.setdefault(fam.key, fam)
    return out


def family_of(cat: dict[str, Any], model_id: str) -> Family | None:
    m = next((m for m in cat.get("models", []) if m["id"] == model_id), None)
    if m is None or not m.get("loras") or not m.get("lora_dirs"):
        return None
    return families({"models": [m]}).get(os.path.basename(m["lora_dirs"][0]))


def display_name(stem: str, title: str | None) -> str:
    if title:
        return title
    name = re.sub(r"[_-]+", " ", stem).strip() or stem
    return name.title() if name == name.lower() else name


def _entry(fam: Family, top: str, rel: str, names: set[str] | None = None) -> Entry | None:
    path = os.path.join(top, *rel.split("/"))
    real = os.path.realpath(path)
    if os.path.commonpath([top, real]) != top or not rel.lower().endswith(EXTS):
        return None
    try:
        st = os.stat(real)
    except OSError:
        return None
    folder, base = os.path.split(path)
    stem = os.path.splitext(base)[0]
    if names is None:
        names = {n for n in (stem + s for s in SIDECARS) if os.path.isfile(os.path.join(folder, n))}
    sidecar = next((os.path.join(folder, stem + s) for s in SIDECARS if stem + s in names), None)
    if sidecar and os.path.commonpath([top, os.path.realpath(sidecar)]) != top:
        sidecar = None
    return Entry(f"{fam.key}/{rel}", rel, real, st.st_size, int(st.st_mtime), st.st_mtime_ns, sidecar)


def _walk(fam: Family, top: str, rel_dir: str, depth: int, out: dict[str, Entry]) -> None:
    try:
        with os.scandir(os.path.join(top, *rel_dir.split("/")) if rel_dir else top) as it:
            items = sorted(it, key=lambda e: e.name)
    except OSError:
        return
    names = {e.name for e in items}
    for e in items:
        rel = f"{rel_dir}/{e.name}" if rel_dir else e.name
        if len(out) >= MAX_FILES:
            return
        if e.is_dir(follow_symlinks=False):
            if fam.recursive and depth < MAX_DEPTH and not e.name.startswith("."):
                _walk(fam, top, rel, depth + 1, out)
        elif e.name.lower().endswith(EXTS) and rel not in out:
            entry = _entry(fam, top, rel, names)
            if entry is not None:
                out[rel] = entry


def scan(fam: Family) -> list[Entry]:
    """Every LoRA of the family; the primary folder wins over linked ones."""
    out: dict[str, Entry] = {}
    for folder in fam.dirs:
        top = os.path.realpath(folder)
        if os.path.isdir(top):
            _walk(fam, top, "", 0, out)
    return list(out.values())


def find(fam: Family, lora_id: str) -> Entry | None:
    key, _, rel = lora_id.partition("/")
    parts = rel.split("/")
    if key != fam.key or "\\" in rel or "\0" in rel or any(p in ("", ".", "..") for p in parts):
        return None
    if len(parts) > 1 and not fam.recursive:
        return None
    for folder in fam.dirs:
        entry = _entry(fam, os.path.realpath(folder), rel)
        if entry is not None:
            return entry
    return None


_info: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}


def info(entry: Entry) -> dict[str, Any]:
    """Header facts, cached by (path, size, mtime); empty facts for unreadable headers."""
    stamp = (entry.size, entry.mtime_ns)
    hit = _info.get(entry.path)
    if hit is None or hit[0] != stamp:
        parsed = header.read(entry.path)
        hit = (stamp, header.summary(*parsed) if parsed else header.summary({}, {}))
        _info[entry.path] = hit
    return hit[1]
