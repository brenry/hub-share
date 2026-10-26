"""Fake `shared.model_dropdowns`: download status, and the files a model expects (upstream's named entries). Like the
real one, it asks for the LoRA folder."""
from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class DropdownDeps:
    get_lora_dir: Callable[[str], str]
    get_local_model_filename: Callable[[str], str | None]
    get_lora_local_path: Callable[[str, str], str]


def get_model_download_status(deps: DropdownDeps, model_type: str) -> int:
    import wgp

    deps.get_lora_dir(model_type)
    return 2 if model_type in wgp.FAKE["available"] else 0


def _urls(model_type: str, prop: str) -> list[str]:
    import wgp

    return [u for u in wgp.get_model_recursive_prop(model_type, prop) if isinstance(u, str) and u]


def get_missing_core_file_entries_for_status(deps: DropdownDeps, model_type: str) -> list[dict]:
    """Like upstream's: the main file the model expects, when it is nowhere; a model the fake marks available has
    every file."""
    import wgp

    if model_type in wgp.FAKE["available"]:
        return []
    return [{"filename": u, "extra_paths": None} for u in _urls(model_type, "URLs")[:1]
            if deps.get_local_model_filename(u) is None]


def get_expected_secondary_file_entries_for_status(deps: DropdownDeps, model_type: str) -> list[dict]:
    """Like upstream's: its preload files by name, its own LoRAs by their path in its LoRA folder."""
    folder = deps.get_lora_dir(model_type)
    return [*({"filename": u} for u in _urls(model_type, "preload_URLs")),
            *({"path": os.path.join(folder, os.path.basename(u))} for u in _urls(model_type, "loras"))]


def get_expected_core_file_entries_for_status(deps: DropdownDeps, model_type: str) -> list[dict]:
    """Like upstream's: the main file the model loads (its first `URLs` entry here), then its text encoder's (the
    first `text_encoder_URLs` entry, looked for in its `text_encoder_folder` too)."""
    import wgp

    model_def = wgp.get_model_def(model_type) or {}
    out = [{"filename": u, "extra_paths": None} for u in _urls(model_type, "URLs")[:1]]
    encoder = model_def.get("text_encoder_URLs")
    if isinstance(encoder, list) and encoder:
        out.append({"filename": encoder[0], "extra_paths": model_def.get("text_encoder_folder")})
    return out
