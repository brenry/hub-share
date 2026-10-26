"""A clip's first frame as its thumbnail: one
ffmpeg run reads one frame at 0 s and scales it, one clip at a time (a lock: never a burst), the WebP kept in the
Hub's in-memory thumbnail store only (nothing on disk). ffmpeg as the engine finds it: FFMPEG_BINARY, the engine
folder's `ffmpeg_bins/ffmpeg`, then PATH; none found or no frame read: no thumbnail (the tile stays as it was)."""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import threading
from pathlib import Path

from PIL import Image

SECONDS = 20                                   # one frame of one clip; past this the clip gets none
_one = threading.Lock()
engine_root: list[str] = [""]                  # the engine's folder, from settings (`runtime`, `apply`)


def program() -> str | None:
    named = os.environ.get("FFMPEG_BINARY", "")
    if named and os.path.isfile(named):
        return named
    bundled = os.path.join(engine_root[0], "ffmpeg_bins", "ffmpeg") if engine_root[0] else ""
    return bundled if bundled and os.path.isfile(bundled) else shutil.which("ffmpeg")


def first_frame(path: Path, size: int) -> bytes | None:
    """The clip's frame at 0 s as WebP, at most `size` px wide; None when it cannot be read."""
    ff = program()
    if ff is None:
        return None
    argv = [ff, "-nostdin", "-v", "error", "-i", str(path), "-frames:v", "1", "-vf", f"scale='min({size},iw)':-2",
            "-f", "image2pipe", "-c:v", "png", "-"]
    with _one:
        try:
            done = subprocess.run(argv, capture_output=True, timeout=SECONDS, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return None
    if done.returncode != 0 or not done.stdout:
        return None
    try:
        with Image.open(io.BytesIO(done.stdout)) as im:
            out = io.BytesIO()
            im.convert("RGB").save(out, "WEBP", quality=80)
            return out.getvalue()
    except (OSError, ValueError):
        return None
