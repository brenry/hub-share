"""Upstream WanGP's weight files, found before it would fetch one (Stage 10).

`lacking(w, model, companions)`: what upstream would fetch before `model` loads, by its own presence calls, none of
which fetches: the main files, module files and text encoder it expects (`model_dropdowns`
`get_missing_core_file_entries_for_status`), the preload files, VAE files and model LoRAs
(`get_expected_secondary_file_entries_for_status`, each looked up as its `download_models` does), the handler's
bundles (`query_model_files` on the definition as the load resolves it, `runtime_def`, through
`shared.utils.download.download_def_missing_files`), and the files the facts
file names for the model (`companions`: Whisper for the speech model). Upstream has no list every model needs.

`guard()`: once the engine is open, every way upstream fetches a weight file raises one line naming the file instead
(the worker is offline; a fetch would fail deep inside a load with the network's words): `shared.utils.download`'s
own Hugging Face download (every file of `download_file` and `process_files_def` goes through it), and the
`huggingface_hub` and `file_download` calls the engine takes at call time, and its plain `download_url` (the SeedVC
component's archive). Stdlib only.
"""
from __future__ import annotations

import importlib
import os
from typing import Any

try:
    from ..faults import Refused
except ImportError:  # run as a script by the engine's Python
    from faults import Refused

LACKS = "Not in the engine's weights: {}"
# What this module reads from the engine (R9 §3; the contract test), each tagged with the line that publishes it.
READS: dict[str, dict[str, str]] = {
    "wgp": dict.fromkeys(("_get_dropdown_deps", "model_dropdowns", "get_model_def", "get_base_model_type",
                          "get_model_handler", "server_config", "transformer_quantization",
                          "text_encoder_quantization"), "upstream"),
    "api": {}, "definition": {}, "settings": {}, "generate_video": {}, "suffixes": {},
}
GUARDED = (("shared.utils.download", "_hf_download"), ("huggingface_hub", "hf_hub_download"),
           ("huggingface_hub", "snapshot_download"), ("huggingface_hub.file_download", "http_get"),
           ("shared.utils.download", "download_url"))     # the SeedVC component's fetch (component.py:44)
NAMES = ("filename", "displayed_filename", "allow_patterns", "repo_id")


def _refuse(call: str) -> Any:
    def refuse(*args: Any, **kwargs: Any) -> None:
        at = 1 if call == "download_url" else 0              # download_url(url, filename): the file it would write
        first = args[at] if len(args) > at and isinstance(args[at], str) else call
        named = next((kwargs[k] for k in NAMES if kwargs.get(k)), first)
        raise Refused(LACKS.format(os.path.basename(str(named).rstrip("/*")) or call))
    return refuse


def guard() -> list[str]:
    """Put the refusal in place of each fetch the engine has; returns the ones put."""
    put = []
    for module, name in GUARDED:
        try:
            target = importlib.import_module(module)
        except ImportError:
            continue
        if hasattr(target, name):
            setattr(target, name, _refuse(name))
            put.append(f"{module}.{name}")
    return put


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [] if value is None else [value]


def runtime_def(w: Any, model_type: str, model_def: dict[str, Any]) -> dict[str, Any]:
    """The definition upstream loads `model_type` with: its handler's `resolve_runtime_model_def`, given the server
    config and the quantization in force, as `load_models` calls it (`wgp.py:4171-4174` at af2ed29). An "Auto"
    choice resolves there (H3's Video VAE: the int8 file when the transformer runs int8), and the load fetches the
    files of the resolved definition."""
    resolve = getattr(w.get_model_handler(model_type), "resolve_runtime_model_def", None)
    if resolve is None:
        return model_def
    config = dict(getattr(w, "server_config", None) or {})
    context = dict(config, transformer_quantization=getattr(w, "transformer_quantization",
                                                            config.get("transformer_quantization", "int8")),
                   text_encoder_quantization=getattr(w, "text_encoder_quantization",
                                                     config.get("text_encoder_quantization", "int8")),
                   mixed_precision=config.get("mixed_precision", "0"), vae_precision="16")
    return resolve(model_def, context)


def lacking(w: Any, model_type: str | None, companions: dict[str, list[str]]) -> list[str]:
    """What `download_models` would fetch before `model_type` loads, as names under the checkpoint folders (a main or
    extra file by its base name, a bundle's file by its path); None: what every model needs, which upstream has not."""
    if model_type is None:
        return []
    deps, menus = w._get_dropdown_deps(), w.model_dropdowns
    out = [os.path.basename(str(e.get("filename"))) for e in menus.get_missing_core_file_entries_for_status(deps,
                                                                                                         model_type)]
    lora_dir = deps.get_lora_dir(model_type)
    for entry in menus.get_expected_secondary_file_entries_for_status(deps, model_type):
        if "path" in entry and not os.path.isfile(str(entry["path"])):
            out.append(os.path.basename(str(entry["path"])))
        elif "filename" in entry and deps.get_local_model_filename(entry["filename"], lora_dir=lora_dir) is None:
            out.append(os.path.basename(str(entry["filename"])))
    model_def = runtime_def(w, model_type, w.get_model_def(model_type) or {})
    base = w.get_base_model_type(model_type)
    query = getattr(w.get_model_handler(model_type), "query_model_files", None)
    if query is not None:
        bundles = query(lambda f: [] if f is None else [f[f.rfind("/") + 1:]], base, model_def)
        out += importlib.import_module("shared.utils.download").download_def_missing_files(_list(bundles))
    locate = importlib.import_module("shared.utils.files_locator").locate_file
    for path in [*companions.get(str(model_type), []), *companions.get(str(base), [])]:
        if locate(path, error_if_none=False) is None:
            out.append(path)
    return list(dict.fromkeys(str(p) for p in out if p))
