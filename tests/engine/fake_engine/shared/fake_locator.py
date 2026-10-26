"""Fake `shared.utils.files_locator` (the real one's lookups over the config's checkpoint folders), published as
`wgp.fl` only when fake_engine.json says `locator`: the fork's companion check runs on an engine that has one."""
from __future__ import annotations

import os


def get_checkpoints_paths() -> list[str]:
    import wgp

    return list(wgp.server_config.get("checkpoints_paths") or ["ckpts", "."])


def locate_file(name: str, error_if_none: bool = True) -> str | None:
    name = os.path.basename(name) if name.startswith("http") else name
    hits = [os.path.join(r, name) for r in get_checkpoints_paths() if os.path.isfile(os.path.join(r, name))]
    return hits[0] if hits else None


def locate_folder(name: str, error_if_none: bool = True) -> str | None:
    hits = [os.path.join(r, name) for r in get_checkpoints_paths() if os.path.isdir(os.path.join(r, name))]
    return hits[0] if hits else None


def get_smart_download_root(force_path: str | None = None) -> str:
    roots = get_checkpoints_paths()
    return next((r for r in roots if force_path and os.path.isdir(os.path.join(r, force_path))), roots[0])
