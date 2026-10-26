"""Favorite folders: Drive folders pinned under Favorites in the Media tree, for quick access.

Nothing is moved, copied or linked: the list of paths is the only record (`media/favorite-folders.json`, a
setting, like the Drive path), in the order they were added, with no limit. A folder renamed, moved or
removed through the Hub takes its entry along; one that went missing some other way stays listed, marked, until it
is taken off (`pin`, `on` false). The list is read and written on the loop; only the look at the Drive
(`check`, `describe`) runs in a thread.
"""
from __future__ import annotations

from typing import Any

from hub.core.api import Ctx, Files, Invalid

DOC = "favorite-folders"
DEFAULT: dict[str, Any] = {"version": 1, "folders": []}
NO_DRIVE = "Choose the Drive folder in Settings → Storage"
NOT_THERE = "That folder is not in the Drive"


def _norm(path: str) -> str:
    return "/".join(p for p in path.split("/") if p)


def paths(ctx: Ctx) -> list[str]:
    saved = ctx.doc(DOC, DEFAULT).get().get("folders")
    return [p for p in saved if isinstance(p, str) and p] if isinstance(saved, list) else []


def check(files: Files, path: str) -> str | None:
    """The folder's relative path as the Drive knows it, or None when it is not there (or there is no Drive)."""
    try:
        found = files.folder_list(path)
    except Invalid:
        return None
    return None if found.get("unset") else str(found["path"])


def describe(files: Files, listed: list[str]) -> list[dict[str, Any]]:
    """Each favorite with its name and whether the folder is there right now."""
    return [{"path": p, "name": p.rpartition("/")[2], "ok": check(files, p) is not None} for p in listed]


def clean(body: dict[str, Any]) -> tuple[str, bool]:
    path, on = body.get("path"), body.get("on", True)
    if not isinstance(on, bool):
        raise Invalid("on", "Send true or false")
    if not isinstance(path, str):
        raise Invalid("path", "Send a folder path")
    return _norm(path), on


def pin(ctx: Ctx, path: str, on: bool) -> list[str]:
    """Add the folder to the list (once, at the end) or take it off. -> the list"""
    kept = [p for p in paths(ctx) if p != path]
    folders = [*kept, path] if on else kept
    ctx.doc(DOC, DEFAULT).patch({"folders": folders})
    return folders


def refuse(files: Files, path: str) -> Invalid:
    """Why a pin was refused: no Drive, not a folder in it, or the Drive itself."""
    if files.folder_list("").get("unset"):
        return Invalid("path", NO_DRIVE)
    return Invalid("path", "The Drive itself is always in the tree" if not path else NOT_THERE)


def _inside(path: str, folder: str) -> bool:
    return path == folder or path.startswith(folder + "/")


def renamed(ctx: Ctx, old: str, new: str) -> None:
    """A folder was renamed or moved: entries at or under its old path follow it."""
    old, new = _norm(old), _norm(new)
    if old == new:
        return
    moved = [new + p[len(old):] if _inside(p, old) else p for p in paths(ctx)]
    ctx.doc(DOC, DEFAULT).patch({"folders": list(dict.fromkeys(moved))})


def removed(ctx: Ctx, folder: str) -> None:
    """A folder was erased: entries at or under it go."""
    folder = _norm(folder)
    ctx.doc(DOC, DEFAULT).patch({"folders": [p for p in paths(ctx) if not _inside(p, folder)]})
