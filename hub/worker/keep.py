"""The engine never erases a weight file (Stage 10).

At every import, upstream deletes "deprecated" model files from any checkpoint root (wgp.py: the "Deprecated models"
loop) and renames one ltx-2 file; the Hub's worker is offline, so a deleted file cannot come back. `hold(roots)`
notes every file then under the roots (a walk of each) and, until `release`, `os.remove`, `os.unlink`, `os.rename`
and `os.replace` leave a noted file as it is: never removed, renamed away or written over. New files are free, so a
page run's downloads still land, and everything outside the roots acts as usual. Each file kept is told on stderr.

`removals(source)`: the module-level calls of a source file (the engine's `wgp.py`) that could remove or move a file
past the hold: a remover reached through a module the hold does not patch, bound by name or called on it
(`send2trash.send2trash(path)`). `os` is patched before the engine imports, so even `from os import remove` binds the
held call, and `shutil` and `pathlib` call through `os`: those are caught. An engine whose import would do otherwise
is refused before it opens (`adapters.upstream.Upstream.prepare`): a pin whose deletion loop leaves `os.remove` is
caught at its first start.

Stdlib only; run by the engine's Python like the rest of the worker, and by `pagerun.py`.
"""
from __future__ import annotations

import ast
import json
import os
import sys
import threading
from collections.abc import Callable, Iterable
from typing import Any

KEPT = "Kept {}: the engine wanted to {} it"
CALLS = ("remove", "unlink", "rename", "replace")
# Names that remove or move a file, at module level, bound from another module or called on one; `os` is patched and
# `shutil`'s and `pathlib`'s calls end in it.
REMOVERS = (*CALLS, "rmtree", "move", "delete", "send2trash", "rmdir", "removedirs", "trash")
THROUGH_OS = ("os", "shutil", "pathlib")
_lock = threading.Lock()
_noted: set[str] = set()
_saved: dict[str, Callable[..., Any]] = {}


# Not weights: a download's working files (Hugging Face's `.cache`, a partial file), which a resumed download must
# still be able to rename into place.
SKIPPED = (".incomplete", ".lock", ".tmp")


def walk(roots: Iterable[str]) -> set[str]:
    """Every file under the roots that exist, by its absolute and its real path (links are not followed down); hidden
    folders and a download's working files are left out."""
    out: set[str] = set()
    for root in roots:
        for top, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in files:
                if name.endswith(SKIPPED) or name.startswith("."):
                    continue
                path = os.path.join(top, name)
                out |= {os.path.abspath(path), os.path.realpath(path)}
    return out


def config_roots(root: str, config: str) -> list[str]:
    """The checkpoint folders an engine config names (relative ones from the engine root): with no model folder
    given, the engine searches, and deletes from, the ones its config holds."""
    try:
        with open(config, encoding="utf-8") as f:
            listed = json.load(f).get("checkpoints_paths")
    except (OSError, ValueError, AttributeError):
        return []
    return [os.path.join(root, str(p)) for p in listed] if isinstance(listed, list) else []


def _path(path: Any, dir_fd: int | None) -> str | None:
    try:
        path = os.fsdecode(path)
        if dir_fd is not None and not os.path.isabs(path):
            path = os.path.join(os.readlink(f"/proc/self/fd/{dir_fd}"), path)
    except (TypeError, ValueError, OSError):
        return None
    return path


def _held(path: Any, dir_fd: int | None = None) -> str | None:
    """The path as given, when the hold keeps it; else None."""
    p = _path(path, dir_fd)
    if p is None or not _noted:
        return None
    return p if os.path.abspath(p) in _noted or os.path.realpath(p) in _noted else None


def _tell(path: str, what: str) -> None:
    sys.stderr.write(KEPT.format(path, what) + "\n")
    sys.stderr.flush()


def _remove(name: str) -> Callable[..., Any]:
    real = _saved[name]

    def remove(path: Any, *args: Any, dir_fd: int | None = None, **kwargs: Any) -> None:
        held = _held(path, dir_fd)
        if held is not None:
            _tell(held, "remove")
            return None
        return real(path, *args, dir_fd=dir_fd, **kwargs)
    return remove


def _move(name: str) -> Callable[..., Any]:
    real = _saved[name]

    def move(src: Any, dst: Any, *args: Any, src_dir_fd: int | None = None, dst_dir_fd: int | None = None,
             **kwargs: Any) -> None:
        held = _held(src, src_dir_fd) or _held(dst, dst_dir_fd)
        if held is not None:
            _tell(held, "move or replace")
            return None
        return real(src, dst, *args, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd, **kwargs)
    return move


def hold(roots: Iterable[str]) -> int:
    """Note every file under the roots and guard them (adding to a hold already on); returns how many files are held
    (by real path)."""
    found = walk(roots)
    with _lock:
        _noted.update(found)
        if not _saved:
            _saved.update({n: getattr(os, n) for n in CALLS})
            os.remove, os.unlink = _remove("remove"), _remove("unlink")
            os.rename, os.replace = _move("rename"), _move("replace")
        return len({os.path.realpath(p) for p in _noted})


def release() -> None:
    """The engine's own calls again, and nothing noted."""
    with _lock:
        for name, real in _saved.items():
            setattr(os, name, real)
        _saved.clear()
        _noted.clear()


def holding() -> bool:
    return bool(_saved)


def removals(source: str) -> list[str]:
    """`source`'s module-level calls (outside any function or class) of a remover the hold cannot catch, each as
    "<call> at line <n>": a remover bound by name from a module other than `os`, `shutil` or `pathlib`, or a remover
    called on such a module (`import send2trash` ... `send2trash.send2trash(p)`)."""
    tree = ast.parse(source)
    bound: set[str] = set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] not in THROUGH_OS:
            bound |= {a.asname or a.name for a in node.names if a.name in REMOVERS}
        elif isinstance(node, ast.Import):
            modules |= {a.asname or a.name.split(".")[0] for a in node.names
                        if a.name.split(".")[0] not in THROUGH_OS}
    out: list[str] = []

    def visit(node: ast.AST) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            return
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in bound:
                out.append(f"{func.id} at line {node.lineno}")
            elif isinstance(func, ast.Attribute) and func.attr in REMOVERS and isinstance(func.value, ast.Name) \
                    and func.value.id in modules:
                out.append(f"{func.value.id}.{func.attr} at line {node.lineno}")
        for child in ast.iter_child_nodes(node):
            visit(child)

    for statement in tree.body:
        visit(statement)
    return out
