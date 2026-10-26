"""The text fields a picture may carry: a PNG `Description` (iTXt) and, on a character, `Voice`, read and
written pixel for pixel.

A picture is only its pixels (`clean`); the exception is these fields, which a module that owns a folder of
pictures (Characters' notes and voice, a storyboard cell's text) keeps inside the file itself. `write` saves
the picture again as PNG holding one field's text and the other field as it was, and nothing else: the colour
profile and transparency stay, every other chunk goes, and a JPEG or WebP it came from is erased. Empty text leaves
no field. Pure file work: no folder policy, no thumbnails; a file that cannot be read raises OSError or ValueError.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, PngImagePlugin

KEY = "Description"
VOICE = "Voice"          # a character's voice, in words (the folder's policy is `characters.py`'s)
KEYS = (KEY, VOICE)
MAX = 16_384             # the core's ceiling on the text, whatever a module's own bound: a size rule, not a policy


def fields(path: Path) -> dict[str, str]:
    """Every field of `KEYS` inside the file that holds text ({} for none, a non-PNG or a file that cannot be read)."""
    if path.suffix.lower() != ".png":
        return {}
    try:
        with Image.open(path) as im:
            info = dict(im.info)
    except (OSError, ValueError):
        return {}
    return {k: str(info[k]) for k in KEYS if isinstance(info.get(k), str) and info[k]}


def read(path: Path, key: str = KEY) -> str:
    """The text of one field inside the file ("" for none, for a file that is not a PNG, or for one that cannot be
    read)."""
    return fields(path).get(key, "")


def write(path: Path, text: str, key: str = KEY) -> Path:
    """Write `path` again as `<stem>.png` holding `text` as its `key` field (none when empty) and the other fields
    of `KEYS` as they were, pixel for pixel. A file of another type is erased once the PNG stands. -> the PNG."""
    if key not in KEYS:
        raise ValueError(f"no text field {key}")
    kept = {**fields(path), key: text}
    dest = path.with_name(f"{path.stem}.png")
    tmp = path.with_name(f".{path.stem}.hub-text")
    try:
        with Image.open(path) as im:
            im.load()
            extra = {k: im.info[k] for k in ("icc_profile", "transparency") if k in im.info}
            if im.mode not in ("1", "L", "LA", "I", "P", "RGB", "RGBA"):
                im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
            info = PngImagePlugin.PngInfo()
            for name in KEYS:
                if kept.get(name):
                    info.add_itxt(name, kept[name])
            im.save(tmp, "PNG", pnginfo=info, **extra)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(dest)
    if path != dest:
        path.unlink(missing_ok=True)
    return dest
