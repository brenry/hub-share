"""The Hub's own media roots in its data folder and the file types each holds; a free time name in one; and what an
older hub left there, erased at start.

`outputs` (Temp, the root "out": pictures), `clips` (MP4s the engine makes) and `sounds` (WAVs the engine
makes) are the Hub's own, created at start; a name in them is the time and nothing else (`temp_path`). `scripts` (the
scripts, one JSON file each) is the Hub's own too, made at start, and holds no media. `sets` (the
stage sets, `<Name>/set.json`, its plates and pans) is the Hub's own too, made at start; its
pictures are images.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from hub.core.api import Invalid

IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
CLIP_TYPES = {".mp4": "video/mp4"}
SOUND_TYPES = {".wav": "audio/wav"}
MEDIA_TYPES = {**IMAGE_TYPES, **CLIP_TYPES, **SOUND_TYPES}
CLIPS = "clips"                                   # the clips root: `<data>/clips`, ids `clips/<day>/<time>.mp4`
SOUNDS = "sounds"                                 # the sounds root: `<data>/sounds`, ids `sounds/<day>/<time>.wav`
SCRIPTS = "scripts"                               # the scripts root: `<data>/scripts/<Name>.json`, no media
SETS = "sets"                                     # the sets root: `<data>/sets/<Name>/`
OWN = ("outputs", CLIPS, SOUNDS, SCRIPTS, SETS)   # the Hub's own roots, by folder name under `<data>`

IN_SET = "A set's plates and pan stay in its set"


def refuse_sets(ids: object) -> None:
    """Media never takes a file out from under a set's record: ids in the sets root are refused."""
    if isinstance(ids, list) and any(isinstance(i, str) and i.split("/", 1)[0] == SETS for i in ids):
        raise Invalid("ids", IN_SET)


def temp_path(outputs: Path, suffix: str, flat: bool = False) -> Path:
    """A free path for a new Temp file (or sound): `<day>/<HHMMSS-mmm>[-n]<suffix>`; `flat` (a clip: no
    subfolders): `<YYYY-MM-DD HHMMSS-mmm>[-n]<suffix>` in the root itself."""
    now = time.time()
    day = time.strftime("%Y-%m-%d", time.localtime(now))
    folder = outputs if flat else outputs / day
    stem = (f"{day} " if flat else "") + time.strftime("%H%M%S", time.localtime(now)) + f"-{int(now * 1000) % 1000:03d}"
    folder.mkdir(parents=True, exist_ok=True)
    for n in range(1, 1000):
        path = folder / f"{stem}{'' if n == 1 else f'-{n}'}{suffix.lower()}"
        if not path.exists():
            return path
    raise Invalid("item", "Could not name the new file")


# What an older hub kept about pictures and prompts in its data folder; erased at start, once, and never written again.
OLDER_RECORDS = ("inputs", "cache", "media/favorites.json", "loras/covers", "loras/thumbs", "core/learned.json",
                 "generate-image/prompts.json")


def forget_older_records(data_dir: Path) -> None:
    for rel in OLDER_RECORDS:
        path = data_dir / rel
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
    for path in (p for own in OWN for p in (data_dir / own).rglob(".*")):   # half taken in
        if path.is_file() and not path.is_symlink():
            path.unlink(missing_ok=True)
