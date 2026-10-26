"""The Settings screen's edit: which settings it may change, the folders checked on disk (`pathrules`) against the
folders in use, then the whole checked again (`settings.validate`)."""
from __future__ import annotations

import copy
from typing import Any

from hub import pathrules
from hub.settings import SettingsError, validate

_EDITABLE = {"vram": {"idle_unload", "idle_minutes", "clip_previews"}, "paths": {"drive", "characters"},
             "engine": {"root", "python", "model_folders", "helper_folders", "profile", "profile_video"},
             "modules": {"loras", "generate-image", "director"}}
_MODULE_EDITABLE = {"generate-image": {"video_tiers"},      # a module's own settings the screen may change
                    "director": {"video_lora_folders"}}     # the Storyboard's own LoRA folders, apart from the rest


def ui_patch(settings: dict, changes: Any, roots: dict[str, str] | None = None) -> dict:
    """Apply a screen's edit: idle unload, Diagnostics, the Drive folder, engine paths and memory profiles, LoRA
    folders, the video sizes offered.

    Paths are checked on disk (`pathrules`); `roots` are the folders in use (Temp, the Drive)."""
    if not isinstance(changes, dict) or set(changes) - {*_EDITABLE, "diagnostics"}:
        raise SettingsError("(edit)", "only idle unload, diagnostics and folders can change here")
    new = copy.deepcopy(settings)
    for section, keys in _EDITABLE.items():
        part = changes.get(section, {})
        if not isinstance(part, dict) or set(part) - keys:
            raise SettingsError(section, f"only {', '.join(sorted(keys))} can change here")
        if section != "modules":
            new[section].update(part)
    if "diagnostics" in changes:
        new["diagnostics"] = changes["diagnostics"]
    for mod_id, keys in _MODULE_EDITABLE.items():
        part = changes.get("modules", {}).get(mod_id, {})
        if not isinstance(part, dict) or set(part) - keys:
            raise SettingsError(f"modules.{mod_id}", f"only {', '.join(sorted(keys))} can change here")
        new["modules"] = {**new["modules"], mod_id: {**new["modules"].get(mod_id, {}), **part}}
    try:
        _check_paths(new, changes, dict(roots or {}))
    except pathrules.Refused as e:
        raise SettingsError(e.field, e.text) from None
    return validate(new)


_ROOT_NAMES = {"temp": "Temp", "drive": "Drive", "characters": "Characters"}


def _check_paths(new: dict, changes: dict, roots: dict[str, str]) -> None:
    eng, paths = changes.get("engine", {}), changes.get("paths", {})
    if "root" in eng:
        new["engine"]["root"] = pathrules.engine_root(eng["root"], "engine.root")
    if "python" in eng:
        new["engine"]["python"] = pathrules.python(eng["python"], "engine.python")
    for key in ("model_folders", "helper_folders"):
        if key in eng:
            new["engine"][key] = pathrules.folders(eng[key], f"engine.{key}")
    loras = changes.get("modules", {}).get("loras")
    if loras is not None:
        if not isinstance(loras, dict) or set(loras) != {"folders"}:
            raise pathrules.Refused("modules.loras", "only folders can change here")
        found = pathrules.folders(loras["folders"], "modules.loras.folders")
        new["modules"] = {**new["modules"], "loras": {**new["modules"].get("loras", {}), "folders": found}}
    hub_own = [roots["temp"]] if roots.get("temp") else []
    for key in ("drive", "characters"):
        if key in paths:
            clearing = key == "characters" and paths[key] == ""       # Characters may be set back to none
            new["paths"][key] = "" if clearing else pathrules.drive_root(paths[key], f"paths.{key}", new, hub_own)
            roots[key] = new["paths"][key]
    edited = [("engine.root", [new["engine"]["root"]])] if "root" in eng else []
    edited += [(f"engine.{k}", new["engine"][k]) for k in ("model_folders", "helper_folders") if k in eng]
    if loras is not None:
        edited.append(("modules.loras.folders", new["modules"]["loras"]["folders"]))
    video = changes.get("modules", {}).get("director", {}).get("video_lora_folders")
    if video is not None:
        found = pathrules.folders(video, "modules.director.video_lora_folders")
        new["modules"]["director"] = {**new["modules"].get("director", {}), "video_lora_folders": found}
        edited.append(("modules.director.video_lora_folders", found))
    for field, items in edited:
        for i, item in enumerate(items):
            for key, root in roots.items():
                if root and pathrules.overlaps(item, root):
                    raise pathrules.Refused(field if field == "engine.root" else f"{field}[{i}]",
                                            f"Overlaps the {_ROOT_NAMES.get(key, key)} folder")
