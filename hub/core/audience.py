"""The scene's audience sounds: the Hub's own files in its sounds root, one per kind,
`sounds/audience/<kind>.wav`. A sound made for a scene is filed there when the name is free (`file_sound`); a sound
from Sounds kept as the audience is copied in there, stripped to its sound, replacing the one there
(`keep_audience`). The kinds are the plan's three words.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from hub.core import drive, sound
from hub.core.api import Invalid
from hub.core.roots import SOUNDS

if TYPE_CHECKING:
    from hub.core.files import Files

FOLDER = "audience"
KINDS = ("applause", "laughter", "gasps")
NOT_A_SOUND = "That is not a sound"
NO_KIND = "Keep it as applause, laughter or gasps"
UNREAD = "That sound could not be read"


def _sound(files: Files, item_id: object) -> Path:
    if not isinstance(item_id, str) or files.kind(item_id) != "sound":
        raise Invalid("id", NOT_A_SOUND)
    return files.existing_media(item_id)


def _folder(files: Files) -> Path:
    folder = files.roots[SOUNDS] / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def file_sound(files: Files, item_id: str, name: str) -> str:
    """A Sounds item moved to `sounds/audience/<name>.wav` when that name is free; a name taken leaves the item where
    it is. -> its id."""
    src = _sound(files, item_id)
    try:
        name = drive.name_ok(name)
    except Invalid:
        raise Invalid("name", "Use a plain sound name, without slashes") from None
    dest = files.roots[SOUNDS] / FOLDER / f"{name}.wav"
    if dest.exists():
        return item_id
    _folder(files)
    files._drop_thumbs(src)
    shutil.move(str(src), str(dest))
    return f"{SOUNDS}/{FOLDER}/{dest.name}"


def keep_audience(files: Files, sound_id: object, kind: object) -> str:
    """A sound from Sounds as the audience's `kind`: copied in as `sounds/audience/<kind>.wav`, stripped, replacing
    the one there. -> its id."""
    if kind not in KINDS:
        raise Invalid("kind", NO_KIND)
    src = _sound(files, sound_id)
    folder = _folder(files)
    tmp = folder / f".{kind}.hub-audience"
    shutil.copyfile(src, tmp)
    try:
        sound.strip(tmp)
    except (OSError, ValueError):
        tmp.unlink(missing_ok=True)
        raise Invalid("id", UNREAD) from None
    os.replace(tmp, folder / f"{kind}.wav")
    return f"{SOUNDS}/{FOLDER}/{kind}.wav"
