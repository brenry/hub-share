"""The facts the controller needs to write its pointer definitions. Stdlib only; reads engine globals, never a
weight file, and never adds to or changes the engine's definitions.

A pointer is an ordinary definition file the controller writes into the engine's own `finetunes` folder (marked
`hub_auto`); the engine reads it when it starts, like any other finetune (wgp.py: the `defaults/*.json` +
`finetunes/*.json` glob, then `init_model_def`). Pointers are left out of every fact here, so the hub's own files
never count as naming a weight file, as a model to match against, or as a taken model id.
"""
from __future__ import annotations

import os
from typing import Any

WEIGHT_EXT = (".safetensors", ".sft", ".gguf")
# What this module reads from the engine (R9 §3; the contract test), each tagged with the line that publishes it.
READS: dict[str, dict[str, str]] = {
    "wgp": {"get_model_recursive_prop": "both", "get_local_model_filename": "both", "models_def": "both",
            "get_base_model_type": "both"},
    "api": {},
    "definition": {"URLs": "both", "path": "both", "hub_auto": "both", "hub_files": "upstream"},
    "settings": {},
    "generate_video": {},
    "suffixes": {},
}


def located(w: Any, deps: Any, root: str, model_type: str) -> list[str]:
    """The model's main weight files (`URLs`) present now, found the way the engine finds them: a URL by its
    base name, a path as it is (an absolute one where it is), joined to the engine's checkpoint folders."""
    urls = w.get_model_recursive_prop(model_type, "URLs", return_list=True) or []
    out = []
    for url in urls if isinstance(urls, list) else [urls]:
        if not isinstance(url, str) or not url:
            continue
        found = deps.get_local_model_filename(os.path.basename(url) if url.startswith("http") else url)
        if found:
            out.append(os.path.normpath(os.path.join(root, found)))
    return list(dict.fromkeys(out))


def _names(value: Any, out: set[str]) -> None:
    if isinstance(value, str):
        if value.lower().endswith(WEIGHT_EXT):
            out.add(os.path.basename(value))
    elif isinstance(value, dict):
        for v in value.values():
            _names(v, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _names(v, out)


def weights(w: Any, deps: Any, root: str, image_types: list[str]) -> dict[str, Any]:
    """`named`: every weight file name the engine's own definitions mention (the engine's own files of the parts
    pointed elsewhere included); `claimed`: {real path: model} of the files they point at; `types`:
    their model types; `models`: each image model with its main files present (none: a chosen file can still be
    that kind), its definition file and its architecture. One definition the engine cannot answer for is skipped, never
    the whole list."""
    own = {t: d for t, d in list(w.models_def.items()) if isinstance(d, dict) and not d.get("hub_auto")}
    named: set[str] = set()
    claimed: dict[str, str] = {}
    for model_type, model_def in list(w.models_def.items()):
        chosen = model_def.get("hub_files") if isinstance(model_def, dict) and isinstance(model_def.get("hub_files"),
                                                                                       dict) else {}
        if model_type in own:
            _names({k: v for k, v in model_def.items() if k not in chosen}, named)   # the chosen files by path, below
        for key in chosen:                                                          # a pointer's choices too
            _claim(model_def.get(key), model_type, claimed)
    models = {}
    for model_type in image_types:
        model_def = own.get(model_type)
        try:
            files = located(w, deps, root, model_type) if model_def is not None else []
            arch = w.get_base_model_type(model_type)
        except Exception:
            continue
        source = _source(root, model_type, model_def) if model_def is not None else None
        if arch and source:          # its main file present or not: a chosen file may be that kind
            models[model_type] = {"files": files, "architecture": str(arch), "source": source}
    return {"named": sorted(named), "types": sorted(own), "models": models, "claimed": claimed}


def _claim(value: Any, model_type: str, out: dict[str, str]) -> None:
    """The files chosen for a model's parts, by their real path: those files are that model's, and
    no other file sharing a name is (a name alone would claim every file called `model.safetensors`)."""
    for item in value if isinstance(value, list) else [value]:
        if isinstance(item, str) and os.path.isabs(item) and os.path.isfile(item):
            out[os.path.realpath(item)] = model_type


def _source(root: str, model_type: str, model_def: dict[str, Any]) -> str | None:
    """The definition file a pointer takes its values from: for a model with chosen files (the
    engine's `path` is then the small `finetunes` file holding only the choices), the engine's own default."""
    path = model_def.get("path")
    if isinstance(model_def.get("hub_files"), dict):
        path = os.path.join("defaults", f"{model_type}.json")
        return os.path.normpath(os.path.join(root, path)) if os.path.isfile(os.path.join(root, path)) else None
    return os.path.normpath(os.path.join(root, path)) if isinstance(path, str) else None
