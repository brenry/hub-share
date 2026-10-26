"""A file the engine looks for in one place is found anywhere in the model folders, by its name.

Upstream looks for some files only inside a folder named after the model: a "file|folder" entry is
`<checkpoint path>/<folder>/<file>` (`shared/utils/files_locator.py:137-152`, `locate_file` `:211-223`), so a model's
`<file>|<folder>` entry is missed in the model folders, which are
sorted by kind (`text_encoders`, `vae`, `diffusion_models`), not by model. The worker wraps the engine's
`locate_file` in memory, as it already does the LoRA-folder lookup: when the engine's own search finds nothing, a
file of exactly that name anywhere under its checkpoint paths (the model folders) is the answer, provided
there is one such file only. A model's own LoRA (its definition's `loras`, looked for only in the model's LoRA
folder: wgp.py `get_lora_local_path` :3836, used by the load at :3800-3802) is found the same way under the LoRA root
and the checkpoint paths. Nothing on disk changes; no file is moved, copied or linked. Stdlib only.
"""
from __future__ import annotations

import importlib
import os
from collections.abc import Callable, Iterable
from typing import Any

LOCATOR = "shared.utils.files_locator"


def index(roots: Iterable[str]) -> dict[str, list[str]]:
    """{file name: its real paths} for every file under `roots` (any depth, hidden folders left out)."""
    out: dict[str, list[str]] = {}
    seen: set[str] = set()
    for root in roots:
        if not os.path.isdir(root):
            continue
        for here, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in files:
                real = os.path.realpath(os.path.join(here, name))
                if real not in seen:
                    seen.add(real)
                    out.setdefault(name, []).append(real)
    return out


def wrap(original: Callable[..., Any], roots: Callable[[], Iterable[str]]) -> Callable[..., Any]:
    """`locate_file` that, when the engine's own search finds nothing, takes the one file of that name under
    `roots()` (built once, at the first miss)."""
    names: dict[str, list[str]] | None = None

    def locate_file(file_name: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal names
        try:
            found = original(file_name, *args, **kwargs)              # the engine's own search, as it was asked
        except Exception:
            found, failed = None, True
        else:
            failed = False
        if found or not isinstance(file_name, str) or (os.path.isabs(file_name) and not file_name.startswith("http")):
            return found if found or not failed else original(file_name, *args, **kwargs)
        if names is None:
            names = index(roots())
        hits = names.get(os.path.basename(file_name.split("|", 1)[0])) or []
        if len(hits) == 1:
            return hits[0]
        return original(file_name, *args, **kwargs) if failed else found

    locate_file.hub_anywhere = True  # type: ignore[attr-defined]
    return locate_file


def wrap_lora(original: Callable[..., Any], roots: Callable[[], Iterable[str]]) -> Callable[..., Any]:
    """`get_lora_local_path` that, when the file is not in the model's LoRA folder, takes the one file of that name
    under `roots()`."""
    names: dict[str, list[str]] | None = None

    def get_lora_local_path(lora_dir: Any, lora: Any) -> Any:
        nonlocal names
        path = original(lora_dir, lora)
        if lora_dir is None or not isinstance(path, str) or os.path.isfile(path):
            return path
        if names is None:
            names = index(roots())
        hits = names.get(os.path.basename(path)) or []
        return hits[0] if len(hits) == 1 else path

    get_lora_local_path.hub_anywhere = True  # type: ignore[attr-defined]
    return get_lora_local_path


def install(w: Any = None) -> bool:
    """Wrap the open engine's `locate_file` (and, given its `wgp`, `get_lora_local_path`) once; False when the
    engine has no locator."""
    try:
        fl = importlib.import_module(LOCATOR)
    except ImportError:
        return False
    current = getattr(fl, "locate_file", None)
    if current is None:
        return False

    def roots() -> list[str]:
        found = [p for p in getattr(fl, "_checkpoints_paths", []) if isinstance(p, str) and os.path.isabs(p)]
        try:
            found.append(os.path.abspath(w.get_lora_root()))
        except Exception:
            pass
        return found

    if not getattr(current, "hub_anywhere", False):
        fl.locate_file = wrap(current, roots)
    lora = getattr(w, "get_lora_local_path", None)
    if lora is not None and not getattr(lora, "hub_anywhere", False):
        w.get_lora_local_path = wrap_lora(lora, roots)
    return True
