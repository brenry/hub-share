"""The engine's own facts in one sterile file (`main.py --dump-engine`): what the Hub reads from the engine, as the
engine publishes it, so the test fake can be rebuilt from a real engine and checked against it; with the settings a
task may hold when the engine says (`accepted_settings`, upstream's).

Read-only: no task is submitted, no model loaded, no weight file opened, no download or presence call made (the
catalog is built through `_Quiet`, which finds no file). The `finetunes/` definitions and the Hub's
pointers (`hub_auto`) are left out whole; paths, config values and file presence are redacted (`redact`). The
engine arguments, the environment, the command line and the login name are never read; the host name and the home
folder serve the last check alone (`sterile`), which refuses to write a file that names any of them. Stdlib only.
"""
from __future__ import annotations

import dataclasses
import importlib
import inspect
import json
import math
import os
import re
import socket
import sys
from types import SimpleNamespace
from typing import Any

try:
    from . import catalog
except ImportError:  # run as a script by the engine's Python
    import catalog

FORMAT = 1
# The engine names the Hub reads that are private or present in one flavour only (R9 1.1), and the rest it reads.
PROBE = ("wan_model", "transformer_type", "_get_dropdown_deps", "get_factory_settings", "get_lora_root",
         "get_lora_search_dirs", "primary_settings", "list_model_defs", "DEFAULT_LORA_ROOT", "get_lora_dir",
         "get_model_handler", "get_model_recursive_prop", "get_local_model_filename", "get_model_download_status",
         "get_model_def", "get_base_model_type", "get_model_family", "models_def", "families_infos", "model_dropdowns",
         "server_config", "WanGP_version", "settings_version", "generate_video", "args", "init", "submit_task")
URL_KEYS = ("URLs", "preload_URLs", "loras")
CATALOG_DROPS = ("root", "loras_root", "checkpoints")
ENTRY_DROPS = ("status", "lora_dirs")


class Leak(Exception):
    """The finished dump names an owner's folder or the host: nothing is written. The text is the one line shown."""


def scalar(value: Any) -> bool:
    return value is None or isinstance(value, (bool, int, str)) or (isinstance(value, float) and math.isfinite(value))


def plain(value: Any) -> Any:
    """A JSON copy: tuples become lists; anything else that is not JSON becomes `<object:TypeName>`."""
    if scalar(value):
        return value
    if isinstance(value, dict):
        return {(k if isinstance(k, str) else str(k) if scalar(k) else f"<object:{type(k).__name__}>"): plain(v)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return f"<object:{type(value).__name__}>"


def public(obj: Any) -> list[str]:
    return sorted(n for n in dir(obj) if not n.startswith("_")) if obj is not None else []


def parameters(fn: Any) -> list[dict[str, Any]] | None:
    """`fn`'s parameters in order: name, kind and default (`<required>` when it has none)."""
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return None
    return [{"name": p.name, "kind": p.kind.name,
             "default": "<required>" if p.default is p.empty else p.default if scalar(p.default)
             else f"<object:{type(p.default).__name__}>"} for p in params]


def shipped(root: str, model_type: str, model_def: dict) -> bool:
    """The definition is the engine's own `defaults/<type>.json`, not overridden by a file in `finetunes/`."""
    own = os.path.join(root, "defaults", f"{model_type}.json")
    path = model_def.get("path")
    if isinstance(path, str):
        return os.path.realpath(os.path.join(root, path)) == os.path.realpath(own)
    return os.path.isfile(own) and not os.path.isfile(os.path.join(root, "finetunes", f"{model_type}.json"))


def lora_key(w: Any, root: str, model_type: str, adapter: Any) -> str | None:
    """The model's LoRA folder relative to the LoRA root; None when outside it or unknown."""
    try:
        path = catalog.lora_dir(w, root, model_type, adapter)
        rel = os.path.relpath(path, os.path.normpath(os.path.join(root, adapter.lora_root(w))))
    except Exception:
        return None
    return None if rel == os.pardir or rel.startswith(os.pardir + os.sep) else rel.replace(os.sep, "/")


def model_facts(w: Any, root: str, model_type: str, adapter: Any) -> dict[str, Any]:
    model_def = w.get_model_def(model_type)
    return {"architecture": plain(w.get_base_model_type(model_type)),
            "family": plain(w.get_model_family(model_type, for_ui=True)),
            "definition": plain(model_def), "settings": plain(model_def.get("settings") or {}),
            "factory": plain(adapter.factory_settings(w, model_type)),
            "lora_key": lora_key(w, root, model_type, adapter)}


def handlers(w: Any, models: dict[str, dict]) -> dict[str, Any]:
    """Per architecture: its handler's public methods and the parameters of its `get_lora_dir`."""
    out: dict[str, Any] = {}
    for model_type, facts in models.items():
        arch = str(facts["architecture"])
        if arch in out:
            continue
        try:
            handler = w.get_model_handler(model_type)
            get_dir = getattr(handler, "get_lora_dir", None)
            out[arch] = {"methods": [n for n in public(handler) if callable(getattr(handler, n, None))],
                         "get_lora_dir": [p["name"] for p in parameters(get_dir) or []] if get_dir else None}
        except Exception:
            out[arch] = None
    return out


def classes(api: Any) -> dict[str, Any]:
    """Every class `shared.api` defines: public attributes, and the field names of a dataclass."""
    out = {}
    for name, cls in sorted(vars(api).items() if api is not None else ()):
        if inspect.isclass(cls) and cls.__module__ == api.__name__:
            out[name] = {"attributes": public(cls),
                         "fields": [f.name for f in dataclasses.fields(cls)] if dataclasses.is_dataclass(cls) else None}
    return out


def file_keys(root: str) -> list[str]:
    try:
        with open(os.path.join(root, "wgp_config.json"), encoding="utf-8") as f:
            config = json.load(f)
    except (OSError, ValueError):
        return []
    return sorted(str(k) for k in config) if isinstance(config, dict) else []


class _Quiet:
    """The engine module as the catalog sees it here: the kept models only, and no file is ever found (no presence
    or download status function is called)."""

    def __init__(self, w: Any, kept: list[str]) -> None:
        self._w = w
        self.models_def = {t: w.models_def[t] for t in kept}
        self.model_dropdowns = SimpleNamespace(get_model_download_status=lambda deps, model_type: 0)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._w, name)

    def _get_dropdown_deps(self) -> Any:
        return SimpleNamespace(get_lora_dir=self._w.get_lora_dir, get_local_model_filename=lambda name: None)


def build(engine: Any) -> dict[str, Any]:
    """The whole dump, before `redact`. `engine` is an opened `wan2gp.Engine`."""
    w, root = engine.w, engine.root
    api = sys.modules.get("shared.api")
    deps = w._get_dropdown_deps()
    objects = {"wgp": w, "shared.api": api, "session": engine.session, "dropdown_deps": deps}
    kept, left = [], {"finetunes": 0, "hub_auto": 0, "unreadable": []}
    for model_type, model_def in sorted(w.models_def.items()):
        if isinstance(model_def, dict) and model_def.get("hub_auto"):
            left["hub_auto"] += 1
        elif isinstance(model_def, dict) and shipped(root, model_type, model_def):
            kept.append(model_type)
        else:
            left["finetunes"] += 1
    models = {}
    for model_type in kept:
        try:
            models[model_type] = model_facts(w, root, model_type, engine.adapter)
        except Exception:
            left["unreadable"].append(model_type)
    seen = [*objects.values(), getattr(w, "model_dropdowns", None)]
    return {
        "format": FORMAT,
        "engine": {"flavour": engine.api, "version": str(w.WanGP_version),
                   "settings_version": plain(w.settings_version)},
        "names": {**{k: public(v) for k, v in objects.items()},
                  "probe": {n: any(o is not None and hasattr(o, n) for o in seen) for n in PROBE}},
        "classes": classes(api),
        "generate_video": parameters(getattr(w, "generate_video", None)),
        "handlers": handlers(w, models),
        "families": plain(getattr(w, "families_infos", None)),
        "primary_settings": plain(getattr(w, "primary_settings", None)),
        "config_keys": {"file": file_keys(root), "memory": sorted(str(k) for k in w.server_config)},
        "models": models,
        "accepted_settings": accepted_settings(),
        "catalog": plain(catalog.build(_Quiet(w, list(models)), root, engine.adapter)),
        "left_out": left,
    }


def accepted_settings() -> list[str] | None:
    """The settings the engine accepts in a task, when it says (upstream's `shared/utils/setting_names`; the upstream
    adapter checks every task against it), sorted; None when it does not."""
    try:
        names = importlib.import_module("shared.utils.setting_names").accepted_setting_names()
    except Exception:
        return None
    return sorted(str(n) for n in names)


def _base_name(text: str) -> str:
    return re.split(r"[\\/]", text.rstrip("/\\"))[-1]


def _pathlike(text: str, roots: list[str]) -> bool:
    return (os.path.isabs(text) or text.startswith(("~", "\\\\")) or bool(re.match(r"[A-Za-z]:[\\/]", text))
            or any(r in text for r in roots))


def redact(doc: dict[str, Any], root: str) -> dict[str, Any]:
    """A copy of the dump with paths, config values and file presence taken out (spec rules 1 to 5)."""
    roots = [r for r in {root, os.path.realpath(root)} if len(r) > 1]

    def walk(value: Any, url: bool) -> Any:
        if isinstance(value, dict):
            return {k: walk(v, url or k in URL_KEYS or k.endswith("_URLs")) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v, url) for v in value]
        if isinstance(value, str) and url:
            return _base_name(value)
        return "<path>" if isinstance(value, str) and _pathlike(value, roots) else value

    out = walk(doc, False)
    for facts in (out.get("models") or {}).values():
        if isinstance(facts.get("definition"), dict):
            facts["definition"].pop("path", None)
    cat = out.get("catalog") or {}
    cat.pop("weights", None)
    for key in CATALOG_DROPS:
        (cat.get("engine") or {}).pop(key, None)
    for entry in cat.get("models") or []:
        for key in ENTRY_DROPS:
            entry.pop(key, None)
        if isinstance(entry.get("video"), dict):
            entry["video"].pop("text_encoders_found", None)
    return out


def needles(root: str, state: str) -> list[re.Pattern[str]]:
    """What the file must not hold: the engine root, the state folder, the home folder (each as given and as its
    real path), and the host name when it has six characters or more (as a whole word)."""
    folders = {p for d in (root, state, os.path.expanduser("~")) for p in (os.path.abspath(d), os.path.realpath(d))}
    texts = {t for p in folders if len(p.rstrip("/\\")) > 1 for t in (p, json.dumps(p, ensure_ascii=False)[1:-1])}
    out = [re.compile(re.escape(t)) for t in sorted(texts)]
    host = socket.gethostname()
    if len(host) >= 6:
        out.append(re.compile(rf"(?<!\w){re.escape(host)}(?!\w)", re.IGNORECASE))
    return out


def _pointer(value: Any, found: list[re.Pattern[str]], at: str = "") -> str | None:
    items = value.items() if isinstance(value, dict) else enumerate(value) if isinstance(value, list) else None
    if items is None:
        return at if isinstance(value, str) and any(p.search(value) for p in found) else None
    for key, item in items:
        here = f"{at}/{str(key).replace('~', '~0').replace('/', '~1')}"
        if isinstance(key, str) and any(p.search(key) for p in found):
            return here
        hit = _pointer(item, found, here)
        if hit is not None:
            return hit
    return None


def sterile(text: str, doc: Any, patterns: list[re.Pattern[str]]) -> str | None:
    """None when `text` holds no pattern; else the JSON pointer of the first hit in `doc` ("" for the whole)."""
    found = [p for p in patterns if p.search(text)]
    return None if not found else _pointer(doc, found) or ""


def write(engine: Any, out: str, state: str) -> None:
    """Build, redact and check the dump, then write it to `out` (through `out.tmp`). Raises Leak, writing nothing,
    when the finished text names a folder or the host."""
    doc = redact(build(engine), engine.root)
    text = json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False)
    hit = sterile(text, doc, needles(engine.root, state))
    if hit is not None:
        raise Leak(f"The engine dump was not written: a folder or host name is left at {hit or '/'}")
    with open(out + ".tmp", "w", encoding="utf-8") as f:
        f.write(text + "\n")
    os.replace(out + ".tmp", out)
