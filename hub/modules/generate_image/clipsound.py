"""A sound the clip follows: a Sounds item the screen sends with a clip.

The clip is the shortest length on the model's lattice that holds the whole sound, so no word at the end is cut.
The engine keeps a sound as the clip's own only when it covers the clip, so a sound shorter than that
length goes as a copy that runs on in silence to it (`sound_pad`), in this module's data folder (`CLAUDE.md`: the
Hub's temp files stay in data/); a copy older than a day goes at the next pad. The sound's own file is only read. Its
length is read from the file itself (`sound_exact`). A model whose catalog entry has no `soundtrack`, a continued
clip, a sound longer than the model's largest window and a sound that does not read are each refused in one line
(the worker refuses the rest).
"""
from __future__ import annotations

import contextlib
import math
import os
import posixpath
import time
from pathlib import Path
from typing import Any

from hub.core.api import Ctx, Invalid, sound_exact, sound_pad

UNREAD = "The Hub cannot read the length of this sound"
NO_SOUND = "{} cannot follow a sound"                 # as the worker's (`tasks.NO_SOUND`)
SOUND_CONTINUE = "A continued clip takes no sound"    # as the worker's (`tasks.SOUND_CONTINUE`)
SOUND_MAX = "{} follows at most {} s of sound in one clip"   # as the worker's (`tasks.SOUND_MAX`)
PADS = "soundpad"                                     # the folder of padded copies, in the module's data
KEEP = 24 * 3600                                      # a padded copy is kept a day: a queued clip still finds its own


def sound(ctx: Ctx, p: dict, ui: dict, held: bool) -> tuple[str, float, str] | None:
    """(the path the engine reads, the clip's seconds, the sound's name) when the press sends one (`p["sound"]`, a
    Sounds item id), else None. The seconds are the clip's length on the lattice (`frames`), which the sound, padded
    when it must be, covers exactly."""
    item = p.get("sound")
    if item in (None, ""):
        return None
    if not isinstance(item, str):
        raise Invalid("sound", UNREAD)
    clip = ui.get("video") or {}
    if not clip.get("soundtrack"):
        raise Invalid("sound", NO_SOUND.format(ui["label"]))
    if held:
        raise Invalid("sound", SOUND_CONTINUE)
    if not ctx.files.sound_facts(item):
        raise Invalid("sound", UNREAD)
    real = Path(os.path.realpath(ctx.files.existing_media(item)))
    try:
        seconds = sound_exact(real)
    except (OSError, ValueError):
        raise Invalid("sound", UNREAD) from None
    if seconds <= 0:
        raise Invalid("sound", UNREAD)
    n, fps = frames(clip, seconds), int(clip["fps"])
    top = int(clip.get("window_max") or clip["frames"]["max"])
    if n > top:
        raise Invalid("sound", SOUND_MAX.format(ui["label"], top // fps))
    return _covering(ctx, real, n, n / fps), n / fps, posixpath.splitext(posixpath.basename(item))[0]


def frames(clip: dict[str, Any], seconds: float) -> int:
    """The clip's frames for a sound: the shortest length on the model's lattice (`min` + `step` × k) that holds the
    whole sound. The worker floors to the same lattice (`tasks._sound`), so these seconds give these frames."""
    lattice = clip["frames"]
    lo, step = int(lattice["min"]), max(1, int(lattice["step"]))
    need = math.ceil(seconds * clip["fps"] - 1e-9)
    return lo if need <= lo else lo + math.ceil((need - lo) / step) * step


def _covering(ctx: Ctx, real: Path, n: int, seconds: float) -> str:
    """The path whose sound covers the clip: the sound's own file when it is long enough, else its padded copy."""
    folder = Path(ctx.data_dir) / PADS
    dest = folder / f"{real.parent.name}-{real.stem}-{n}.wav"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        now = time.time()
        for old in folder.glob("*.wav"):
            with contextlib.suppress(OSError):
                if old != dest and now - old.stat().st_mtime > KEEP:
                    old.unlink()
        return str(dest) if sound_pad(real, dest, seconds) else str(real)
    except (OSError, ValueError):
        raise Invalid("sound", UNREAD) from None
