"""A Wan2GP root as the Hub's controller reads it, with no worker running: the entries whose change changes its
catalog (`watch`, the cache key's: `hub/core/enginecat.py`), and a Hub pointer as the engine line keeps it: a finetune
definition file in the engine's `finetunes` folder (`{"model": {...}, **settings}`), which both lines load at start
like any finetune (`glob("finetunes/*.json")`, then the family handler's `query_model_def`; upstream wgp.py:3377).
The Hub's registry (`hub/core/autoreg.py`) asks the root's adapter (`Adapter.pointers`) for every part of this form;
it names none of it itself.

A pointer holds the architecture only (the handler fills in the rest from it) and the file, then the defaults the
screen starts from; nothing else: a copied model field such as `image_ref_choices` makes the handler want helper files
(pose models) and fetch them. A pointer in any other form (an older hub's) is stale and written again. Stdlib only.
"""
from __future__ import annotations

import os
from typing import Any

FOLDER = "finetunes"
POINTER_KEYS = frozenset({"name", "description", "architecture", "URLs", "hub_auto", "hub_file", "hub_base"})
CHOSEN = "hub_files"         # the file choices in a pointer (`modelfiles.MARK`)
SETTINGS_KEYS = ("num_inference_steps", "guidance_scale", "resolution")
PLAIN = frozenset({"name", "description", "architecture", "URLs"})
WATCH = ("wgp.py", "defaults", FOLDER, "ckpts")       # the code, the definitions and the root's own weights
DESCRIPTION = "{path}, set up like {base}. Written by the Hub and deleted by it when the file goes; safe to delete."


def folder(root: str) -> str:
    """Where the engine reads finetune definitions from (relative to its root, its working folder)."""
    return os.path.join(root, FOLDER)


def watch(root: str) -> list[str]:
    return [os.path.join(root, name) for name in WATCH]


def model(definition: Any) -> dict[str, Any] | None:
    """A definition file's model part, when it is one."""
    part = definition.get("model") if isinstance(definition, dict) else None
    return part if isinstance(part, dict) else None


def ours(definition: Any) -> bool:
    """A pointer the Hub wrote (marked `hub_auto`)."""
    part = model(definition)
    return bool(part and part.get("hub_auto"))


def points_at(definition: dict[str, Any]) -> tuple[str, str]:
    """The weight file a pointer names and the model it is set up like."""
    part = model(definition) or {}
    return str(part.get("hub_file") or ""), str(part.get("hub_base") or "")


def stale(definition: dict[str, Any]) -> bool:
    """A pointer in another form than `document` writes (an older hub's, with copied model fields); the file
    choices in it (`modelfiles`, `hub_files` and the parts it names) are choices, not copied fields."""
    part = model(definition) or {}
    chosen = part.get(CHOSEN) if isinstance(part.get(CHOSEN), dict) else {}
    return bool(set(part) - POINTER_KEYS - {CHOSEN, *chosen} or set(definition) - {"model", *SETTINGS_KEYS})


def names_its_file(definition: dict[str, Any]) -> bool:
    """The definition lists its own files (not one borrowing another model's to add a LoRA or a module)."""
    return isinstance((model(definition) or {}).get("URLs"), list)


def extras(definition: dict[str, Any]) -> int:
    """How many entries beyond the plain ones a definition holds (a pointer set up like it leaves them behind)."""
    return len(set(model(definition) or {}) - PLAIN)


def title(definition: dict[str, Any], fallback: str) -> str:
    return str((model(definition) or {}).get("name") or fallback)


def document(path: str, name: str, base: str, architecture: str, like: dict[str, Any]) -> dict[str, Any]:
    """The pointer for the weight file `path`, set up like the model `base` (its definition file: `like`)."""
    pointer = {"name": name, "description": DESCRIPTION.format(path=path, base=title(like, base)),
               "architecture": architecture, "URLs": [path], "hub_auto": True, "hub_file": path, "hub_base": base}
    return {"model": pointer, **{key: like[key] for key in SETTINGS_KEYS if key in like}}
