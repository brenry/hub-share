"""A part's slice of the mixed track, cut with the stdlib `wave` (PCM is cut, not encoded: no ffmpeg).

For a part starting at `start_ms` and rendering `F` frames at `fps`: start sample `S = round(start_ms / 1000 * rate)`,
length `L = ceil(F * rate / fps)` samples, the rate the file's own; read with `setpos(S)` / `readframes(L)` (its own
span only), silence after the track's end, written atomically to `<data>/first-cut/slices/<key16>.wav` (`key16`: the
first 16 hex of sha256 over the track's name, size, mtime_ns, S and L), reused when it is there. The slice runs `F`
frames, past the part into the next shot's sound, so the engine keeps it as the clip's own (it covers the clip); the
extra frames are trimmed at the join. These are the Hub's own temp files in its data folder (CLAUDE.md): slices older
than a day go at each Render and at start, a job's own at its finish (or at once when the queue refuses it). A
part's key holds the slice's `digest` (its samples), never the track's name or time.
"""
from __future__ import annotations

import contextlib
import hashlib
import math
import os
import time
import wave
from pathlib import Path
from typing import NamedTuple

from hub.core.api import Ctx, Invalid

FOLDER = "slices"
KEEP = 24 * 3600
UNREAD = "{} does not read as a PCM WAV"


class Slice(NamedTuple):
    path: Path
    start: int       # S, in samples
    length: int      # L, in samples


def _rate(track: Path) -> int:
    try:
        with wave.open(str(track), "rb") as w:
            return int(w.getframerate())
    except (OSError, EOFError, wave.Error):
        raise Invalid("track", UNREAD.format(track.name)) from None


def where(ctx: Ctx, track: Path, size: int, mtime_ns: int, start_ms: float, frames: int, fps: float) -> Slice:
    """The slice's path and span (nothing written; the track's header read for its rate)."""
    rate = _rate(track)
    start = round(start_ms / 1000 * rate)
    length = math.ceil(frames * rate / fps - 1e-9)
    key = hashlib.sha256(f"{track.name}\0{size}\0{mtime_ns}\0{start}\0{length}".encode()).hexdigest()[:16]
    return Slice(Path(ctx.data_dir) / FOLDER / f"{key}.wav", start, length)


def samples(track: Path, part: Slice) -> tuple[int, int, int, bytes]:
    """(channels, sample width, rate, the PCM of samples `S .. S + L`, silence past the track's end)."""
    try:
        with wave.open(str(track), "rb") as src:
            channels, width, rate, total = src.getnchannels(), src.getsampwidth(), src.getframerate(), src.getnframes()
            got = b""
            if part.start < total:
                src.setpos(part.start)
                got = src.readframes(min(part.length, total - part.start))
    except (OSError, EOFError, wave.Error):
        raise Invalid("track", UNREAD.format(track.name)) from None
    zero = (b"\x80" if width == 1 else b"\x00" * width) * channels
    return channels, width, rate, got + zero * (part.length - len(got) // (width * channels))


def digest(track: Path, part: Slice) -> str:
    """What the slice holds (its format and its samples), hashed: a part's sound in its key, so a re-mix that leaves
    this span as it was leaves the part's key as it was."""
    channels, width, rate, data = samples(track, part)
    return hashlib.sha256(f"{channels}\0{width}\0{rate}\0".encode() + data).hexdigest()


def cut(track: Path, part: Slice) -> Path:
    """The slice written (or reused when there): samples `S .. S + L` of the track, silence past its end."""
    if part.path.is_file():
        return part.path
    channels, width, rate, data = samples(track, part)
    part.path.parent.mkdir(parents=True, exist_ok=True)
    tmp = part.path.with_name(f".{part.path.stem}.{os.getpid()}.tmp")
    try:
        with wave.open(str(tmp), "wb") as dst:
            dst.setnchannels(channels)
            dst.setsampwidth(width)
            dst.setframerate(rate)
            dst.writeframes(data)
        os.replace(tmp, part.path)
    except (OSError, wave.Error):
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise Invalid("track", UNREAD.format(track.name)) from None
    return part.path


def sweep(ctx: Ctx) -> None:
    """Slices older than a day removed (at each Render)."""
    folder, now = Path(ctx.data_dir) / FOLDER, time.time()
    for old in folder.glob("*.wav") if folder.is_dir() else ():
        with contextlib.suppress(OSError):
            if now - old.stat().st_mtime > KEEP:
                old.unlink()


def remove(paths: list[str]) -> None:
    for p in paths:
        with contextlib.suppress(OSError):
            Path(p).unlink()
