"""The engine catalog as the hub keeps it: its cache key, the cache file, the LoRA folders; a worker's
progress as a job reports it; and a finished picture, clip or sound moved from the worker's outbox into its root.

The key changes when the engine, its arguments, its model definitions or its weight folders
change (folder mtimes, one level down too), so a model whose files appear is listed next time. Which entries of the
engine's root hold its code and definitions is the engine line's: the root's adapter names them (`watch`), read here
as a library, so the cached catalog is served without a worker.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PIL import Image

from hub.core import clean, clip, sound
from hub.core.files import CLIP_TYPES, CLIPS, IMAGE_TYPES, SOUND_TYPES, SOUNDS, temp_path
from hub.core.supervisor import EngineFailed
from hub.worker import adapters
from hub.worker import catalog as worker_catalog

OUTPUT_ID = "out"                         # <data>/outputs is the media root "out"


def watched(root: str) -> list[Path]:
    """The root's entries whose change changes its catalog, as the adapter that drives it names them (none for a
    root no adapter drives)."""
    try:
        return [Path(p) for p in adapters.select(root).pointers.watch(root)] if root else []
    except adapters.NoAdapter:
        return []


def catalog_key(engine: Mapping[str, Any]) -> str:
    root = Path(str(engine.get("root") or ""))
    folders = [Path(f) for f in (*engine.get("model_folders", []), *engine.get("helper_folders", []))]
    marks = [f"shape:{worker_catalog.SHAPE}", str(engine.get("python")), str(root), *engine.get("args", []),
             *map(str, folders)]                             # the entry shape: an older cache is never served
    own = watched(str(engine.get("root") or ""))
    subfolders: list[Path] = []
    for folder in (*own, *folders):               # weights often sit one folder down
        with contextlib.suppress(OSError), os.scandir(folder) as it:
            subfolders += sorted(Path(e.path) for e in it if e.is_dir(follow_symlinks=False))
    for path in (*own, *folders, *subfolders):
        try:
            marks.append(f"{path.name}:{path.stat().st_mtime_ns}")
        except OSError:
            marks.append("-")
    return hashlib.sha256("\0".join(marks).encode()).hexdigest()[:16]


def read_cache(path: Path, key: str) -> dict[str, Any] | None:
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return cached.get("catalog") if isinstance(cached, dict) and cached.get("key") == key else None


def write_cache(path: Path, key: str, catalog: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")   # two writers never share a temp file
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps({"key": key, "catalog": catalog}))
    os.replace(tmp, path)


def with_lora_roots(model: dict[str, Any], roots: list[str]) -> dict[str, Any]:
    """Adds `lora_extra`: the model's family folder inside each LoRA folder in Settings."""
    dirs = [os.path.normpath(d) for d in model.get("lora_dirs") or []]
    if not roots or not dirs or not model.get("loras"):
        return model
    key = os.path.basename(dirs[0])
    extra = [p for p in (os.path.normpath(os.path.join(r, key)) for r in roots) if p not in dirs]
    return {**model, "lora_extra": extra}


def progress(msg: Mapping[str, Any], k: int, n: int, frac: float) -> tuple[float, dict[str, Any]]:
    """A worker's progress for image k of n as the job reports it: pct covers the whole job and never goes back;
    loading phases do not move it. Returns the new fraction of image k and the event."""
    steps, step, phase = msg.get("steps") or 0, msg.get("step") or 0, str(msg.get("phase") or "")
    if steps and "load" not in phase:
        frac = max(frac, min(step / steps, 1.0))
    return frac, {"task": k, "of": n, "phase": phase, "step": msg.get("step"), "steps": msg.get("steps"),
                  "pct": int((k - 1 + frac) / n * 100), "text": msg.get("text") or ""}


def link_or_copy(src: Path, dst: Path) -> None:
    """Place `src` at `dst` without ever replacing an existing file."""
    try:
        os.link(src, dst)
    except OSError as exc:
        if isinstance(exc, FileExistsError) or exc.errno != 18:  # 18: EXDEV, another filesystem
            raise
        tmp = dst.with_name(f".{dst.name}.tmp")
        shutil.copyfile(src, tmp)
        try:
            os.link(tmp, dst)
        finally:
            tmp.unlink()


def sweep(outbox: Path) -> None:
    """Whatever a task left in the outbox besides what landed (a sidecar, a half-written file): gone."""
    for path in outbox.glob("*"):
        if path.is_file() and not path.is_symlink():
            path.unlink(missing_ok=True)
        elif path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)


def land(src: str, outbox: Path, outputs: Path, clips: Path | None = None, sounds: Path | None = None
         ) -> dict[str, Any]:
    """Move one finished file from the outbox into its root; -> {id, kind, w, h} (+ seconds for a clip; {id, kind,
    seconds} for a sound). A picture lands in Temp, its metadata cut; an MP4 lands in the clips root, its tags cut,
    its size and length read from its boxes (its frames are never decoded); a WAV lands in the sounds root, every
    chunk but its sound cut (`sound.strip`); anything else fails the job. Each lands in its root's day folder.
    The name is the time and the file is its content: nothing about it is in either."""
    path = Path(os.path.realpath(src))
    if path.parent != Path(os.path.realpath(outbox)) or not path.is_file():
        raise EngineFailed("runtime", "The engine wrote an image outside its outbox")
    suffix = path.suffix.lower()
    if suffix in CLIP_TYPES:
        try:
            clip.strip(path)                                  # CLIP_TYPES is MP4 only
            seen = clip.facts(path)
        except (OSError, ValueError):
            path.unlink(missing_ok=True)
            raise EngineFailed("runtime", "The engine wrote a clip the hub could not read") from None
        root = clips if clips is not None else outputs.with_name(CLIPS)
        dest = temp_path(root, suffix, flat=True)
        link_or_copy(path, dest)
        path.unlink()
        return {"id": f"{CLIPS}/{dest.relative_to(root).as_posix()}", "kind": "clip", "w": seen["w"], "h": seen["h"],
                "seconds": seen["seconds"]}
    if suffix in SOUND_TYPES:
        try:
            sound.strip(path)
            seconds = sound.facts(path)["seconds"]
        except (OSError, ValueError):
            path.unlink(missing_ok=True)
            raise EngineFailed("runtime", "The engine wrote a sound the hub could not read") from None
        root = sounds if sounds is not None else outputs.with_name(SOUNDS)
        dest = temp_path(root, suffix)
        link_or_copy(path, dest)
        path.unlink()
        return {"id": f"{SOUNDS}/{dest.relative_to(root).as_posix()}", "kind": "sound", "seconds": seconds}
    if suffix not in IMAGE_TYPES:
        path.unlink(missing_ok=True)
        raise EngineFailed("runtime", "The engine wrote a file the hub does not take")
    try:
        clean.strip(path)
    except (OSError, ValueError):
        path.unlink(missing_ok=True)
        raise EngineFailed("runtime", "The engine wrote a picture the hub could not read") from None
    dest = temp_path(outputs, suffix)
    link_or_copy(path, dest)
    path.unlink()
    try:
        with Image.open(dest) as im:
            w, h = im.size
    except (OSError, ValueError):
        w = h = None
    return {"id": f"{OUTPUT_ID}/{dest.relative_to(outputs).as_posix()}", "kind": "image", "w": w, "h": h}
