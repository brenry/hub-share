"""Apply a settings edit live: media roots, engine paths and memory profiles, model and LoRA folders.

Nothing here creates, moves or deletes a folder or a file. Items left in an old media
folder simply stop being listed.
"""
from __future__ import annotations

import copy
from types import MappingProxyType
from typing import TYPE_CHECKING

from hub.core import clipthumb
from hub.settings import characters_root, drive_root, storyboards_folder

if TYPE_CHECKING:
    from hub.core.runtime import Core

ENGINE_KEYS = ("root", "python", "model_folders", "helper_folders", "profile", "cc", "cxx")   # read at its start
# `profile_video` restarts nothing now: the lane compares it with the running worker's before each job
LORA_EVENT = "settings.lora_folders"


def lora_folders(settings: dict) -> list[str]:
    return list(settings["modules"].get("loras", {}).get("folders", []))


async def apply(core: Core, old: dict) -> None:
    new = core.settings
    if drive_root(new) != drive_root(old):
        core.files.set_drive(drive_root(new))
    if characters_root(new) != characters_root(old):
        core.files.set_characters(characters_root(new))
    if storyboards_folder(new) != storyboards_folder(old):
        core.files.set_storyboards(storyboards_folder(new))
    clipthumb.engine_root[0] = str(new["engine"].get("root") or "")
    engine_changed = any(old["engine"][k] != new["engine"][k] for k in ENGINE_KEYS)
    loras_changed = lora_folders(old) != lora_folders(new)
    edited = old["engine"] != new["engine"] or loras_changed
    for lane in list(core.book.lanes.values()):
        configure = getattr(lane, "configure", None)
        if configure is not None and edited:
            await configure(new["engine"], lora_folders(new), restart=engine_changed)
    for mod_id, ctx in core.ctxs.items():
        ctx.settings = MappingProxyType(copy.deepcopy(dict(new["modules"].get(mod_id, {}))))
    if loras_changed:
        core.events.emit(LORA_EVENT, {"folders": lora_folders(new)})
