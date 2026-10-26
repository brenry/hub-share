"""The engine's config as the worker seeds it (`<state>/config/wgp_config.json`), from the engine root's own.

Engine-side, stdlib only: run by the engine's Python like the rest of the worker.
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
from typing import Any

# The engine's config is read, not written; these keys never carry over, and these values hold at runtime whatever the
# file or the engine's own migration says: plain PNGs with no metadata, no prompt enhancer, no plugins, no
# notifications, no queue written out after an error (it would hold the prompts). The prompt reaches the
# model unchanged.
DROPPED_CONFIG = ("services", "llm_engines", "enabled_plugins", "installed_remote_plugins")
FORCED_CONFIG: dict[str, Any] = {"image_output_codec": "png", "metadata_type": "none", "enhancer_enabled": 0,
                                 "enhancer_mode": 1, "enabled_plugins": [], "save_queue_if_crash": 0,
                                 "embed_source_images": False, "video_container": "mp4"}
# The memory profile, when set, under every key the engine reads it from: `profile`, and the per-output
# profiles current engines derive from it only when absent (a config the engine wrote already holds them).
# Audio keeps the engine's own.
PROFILE_KEYS = ("profile", "video_profile", "image_profile")


def tidy_scratch(scratch: str) -> None:
    """A failed fetch leaves an empty folder (and a .cache) in the scratch folder; the engine then takes that empty
    folder as the home of a whole helper bundle, and a complete copy in another folder is never looked at. So the
    scratch folder keeps only real files: the cache and every empty folder go, at every worker start."""
    shutil.rmtree(os.path.join(scratch, ".cache"), ignore_errors=True)
    for top, dirs, files in os.walk(scratch, topdown=False):
        if top != scratch and not dirs and not files:
            with contextlib.suppress(OSError):
                os.rmdir(top)


HOME_NAME = "engine-home"                  # the worker's HOME the controller sets: <data>/engine-home (`make_spawn`)


def own_tmp() -> list[str]:
    """The worker's temp folder (`TMPDIR`, which the controller sets to `<data>/engine-home/tmp`) when
    it is exactly that folder of the Hub's, emptied at each start like the outbox; [] for any other (a command run by
    hand from a shell, a test): another TMPDIR is never emptied."""
    tmp, home = os.environ.get("TMPDIR"), os.environ.get("HOME")
    if not tmp or not home or os.path.basename(os.path.abspath(home)) != HOME_NAME:
        return []
    return [tmp] if os.path.abspath(tmp) == os.path.join(os.path.abspath(home), "tmp") else []


def search_paths(config_dir: str, model_folders: list[str]) -> list[str]:
    """The engine looks for a weight file in each listed folder (not deeper). The model folders and
    their first-level subfolders are all searched; the first entry is the engine's write target, so it
    is a hub scratch folder and never a model folder."""
    scratch = os.path.join(config_dir, "ckpts")
    os.makedirs(scratch, exist_ok=True)
    tidy_scratch(scratch)
    paths = [scratch]
    for folder in model_folders:
        paths.append(folder)
        try:
            subs = sorted(e.path for e in os.scandir(folder) if e.is_dir(follow_symlinks=False))
        except OSError:
            subs = []
        paths.extend(subs)
    return paths


def seed_config(root: str, config_dir: str, outbox: str, model_folders: list[str],
                profile: float | None = None, forced: dict[str, Any] | None = None) -> str:
    """Write the hub's own wgp_config.json, based on the engine's (secrets dropped); `profile`, the memory
    profile set (None: the engine config's own stays); `forced`, what the engine line's adapter needs on top.

    It must exist before start: otherwise the engine falls back to reading the root's
    config and writes the result into the hub's config.
    """
    config: dict[str, Any] = {"attention_mode": "auto", "transformer_types": [], "compile": "",
                              "transformer_quantization": "int8", "text_encoder_quantization": "int8"}
    try:
        with open(os.path.join(root, "wgp_config.json"), encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            config = loaded
    except (OSError, ValueError):
        pass
    for key in list(config):
        if key.startswith("notification_") or key in DROPPED_CONFIG:
            del config[key]
    config.update(FORCED_CONFIG, **(forced or {}), save_path=outbox, image_save_path=outbox, audio_save_path=outbox,
                  mesh_save_path=outbox)
    if profile is not None:
        config.update(dict.fromkeys(PROFILE_KEYS, int(profile) if profile == int(profile) else profile))
    if model_folders:
        config["checkpoints_paths"] = search_paths(config_dir, model_folders)
    os.makedirs(config_dir, exist_ok=True)
    path = os.path.join(config_dir, "wgp_config.json")
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return path
