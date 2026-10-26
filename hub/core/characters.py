"""Characters: the folder of named pictures (`Files.roots["chars"]`, Settings → Storage → Characters).

A character is one picture file at the top of that folder; its name is the file name without the extension
(`Character 1.png` is Character 1). The folder's layout is left as it is: the Hub lists it, finds a character by name
(any case), puts a picture under a name — a copy, its metadata cut out — replacing the picture that had that
name, renames a character (the file is renamed) and deletes one (its file is erased, with any older file of the same
name). Nothing else is kept about a character: the file is the record, and its thumbnails go with it.

The one exception to "a picture is its pixels": a character may carry notes typed on it (what the picture does
not show: where it lives, what it wears, how it behaves) and the words for the character's voice, two
PNG text fields (`Description`, `Voice`) inside the character's own file, read by the assistant through
`list_characters`. Saving notes writes the file again as PNG (pixel for pixel; a JPEG or WebP becomes `<name>.png`).
The notes belong to the name: a rename and a new picture put under the name keep them; a picture coming in under a new
name starts with none (`clean.strip` cuts everything). A character may also have its voice as a sound beside its
picture, `<Name>.wav` (a sound kept from Sounds, `keep_voice`, or a recording sent by the
browser as a WAV, `put_sample`, stripped, replacing the one the character had); it goes with the
character's name: renamed with it, erased with it. And its views: more pictures of the character named
`<Name>.<view>.<ext>` beside its picture (`Character 1.side.png`), one word of letters and digits for the view; not
characters, listed under the character, renamed and erased with it; a dotted stem with no listed character before it
stays a character of its own. And its folder `<Name>/` beside its picture: its approved sheet, orbit and
bits, with `casting.json`, its record written only on its Approve; never listed (only the folder's top is read),
renamed and erased with the character.
This file keeps the listing and the policy (its own names, texts and bound); putting, renaming and writing the text
are `named.py`'s, shared with the other folders of named pictures.
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from hub.core import drive, named, pngtext, sound
from hub.core.api import Invalid

if TYPE_CHECKING:
    from hub.core.files import Files

NO_FOLDER = named.NO_CHARS
NOTES_KEY = pngtext.KEY
notes_of = pngtext.read                                         # the notes inside a character's file
SAMPLE = ".wav"                                                 # a character's voice sample, beside its picture
MIN_SAMPLE = 2                                                  # seconds of the engine's least (R22:150)
UNREAD = "That sound file could not be read"
TAKEN = "A character is already called {}"
_VIEW = re.compile(r"[A-Za-z0-9]{1,24}")                        # a view's word
root = named.chars_root
_pictures = named.pictures
_named = named.named


def samples(folder: Path, name: str) -> list[Path]:
    """The voice samples at the top of the folder with that stem (any case)."""
    with os.scandir(folder) as it:
        return [Path(e.path) for e in it if not e.name.startswith(".") and e.is_file()
                and e.name.lower().endswith(SAMPLE) and Path(e.name).stem.casefold() == name.casefold()]


def folder_of(folder: Path, name: str) -> Path | None:
    """The character's folder `<Name>/` at the top of Characters (any case, not a link), else None."""
    want = name.casefold()
    with os.scandir(folder) as it:
        return next((Path(e.path) for e in it if not e.name.startswith(".") and e.is_dir(follow_symlinks=False)
                     and e.name.casefold() == want), None)


def _view_of(stem: str, names: set[str]) -> tuple[str, str] | None:
    """(character stem, view) when `stem` is `<listed name>.<view>` (`_VIEW`), else None."""
    head, dot, view = stem.rpartition(".")
    return (head, view) if dot and head.casefold() in names and _VIEW.fullmatch(view) else None


def views(folder: Path, name: str) -> list[Path]:
    """The view pictures of the character called `name` (any case), by view name."""
    want = name.casefold()
    return sorted((p for p in _pictures(folder) if (v := _view_of(p.stem, {want})) and v[0].casefold() == want),
                  key=lambda p: p.stem.casefold())


def listing(files: Files) -> list[dict]:
    """[{name, id, notes, voice, sample, views: [{id, view}]}] sorted by name (`sample`: it has `<Name>.wav`); empty
    when the folder is not chosen. A view picture is listed under its character, never as one."""
    if "chars" not in files._real:
        return []
    folder, names = root(files), {}
    pictures = _pictures(folder)
    stems = {p.stem.casefold() for p in pictures}
    for p in pictures:
        view = _view_of(p.stem, stems)
        if view is None and p.stem.casefold() not in names:
            text = pngtext.fields(p)
            names[p.stem.casefold()] = {"name": p.stem, "id": f"chars/{p.name}", "notes": text.get(NOTES_KEY, ""),
                                        "voice": text.get(pngtext.VOICE, ""), "sample": bool(samples(folder, p.stem)),
                                        "views": [{"id": f"chars/{v.name}", "view": v.stem.rpartition(".")[2]}
                                                  for v in views(folder, p.stem)]}
    return sorted(names.values(), key=lambda c: c["name"].casefold())


def find(files: Files, name: str) -> str | None:
    """The id of the character called `name` (any case), else None."""
    want = name.strip().casefold()
    return next((c["id"] for c in listing(files) if c["name"].casefold() == want), None)


def put(files: Files, name: object, item_id: str) -> str:
    """Make `item_id`'s picture the character called `name` (`named.put` into "chars": a copy, metadata cut out,
    replacing whatever picture had that name, its notes kept). -> the character's id."""
    return named.put(files, "chars", name, item_id)


def _own(files: Files, item_id: object) -> tuple[Path, Path]:
    """The Characters folder and the character's file, from its id (`chars/<file>`)."""
    folder = root(files)
    if not isinstance(item_id, str) or not item_id.startswith("chars/") or "/" in item_id[6:]:
        raise Invalid("id", "Not a character")
    src = folder / item_id[6:]
    if src.parent != folder or not src.is_file():
        raise Invalid("id", "That character is not in the Characters folder now")
    return folder, src


def rename(files: Files, item_id: object, name: object) -> str:
    """The character's file takes the new name (`named.rename`: its type and notes kept, the old name gone). A name
    another character has is refused. -> the new id."""
    folder, src = _own(files, item_id)
    own, want = folder_of(folder, src.stem), drive.name_ok(name)
    there = folder_of(folder, want)
    if there is not None and there != own:                      # another's folder: refused, folder or none
        raise Invalid("name", f"A folder called {there.name} is in Characters already")
    new_id = named.rename(files, item_id, name, TAKEN)
    new = Path(new_id).stem
    for p in samples(folder, src.stem):                         # its voice goes with its name
        os.replace(p, folder / f"{new}{SAMPLE}")
    for p in views(folder, src.stem):                           # and its views
        files._drop_thumbs(p)
        os.replace(p, folder / f"{new}.{p.stem.rpartition('.')[2]}{p.suffix}")
    if own is not None:                                         # and its folder
        _forget(files, own)
        os.replace(own, folder / new)
    return new_id


def remove(files: Files, item_id: object) -> str:
    """Erase the character: its file, any older file of the same name and its voice sample, at once, no trash. -> the
    name."""
    folder, src = _own(files, item_id)
    for p in _named(folder, src.stem):
        files._drop_thumbs(p)
        p.unlink(missing_ok=True)
    for p in [*samples(folder, src.stem), *views(folder, src.stem)]:
        files._drop_thumbs(p)
        p.unlink(missing_ok=True)
    if (own := folder_of(folder, src.stem)) is not None:       # and its folder
        _forget(files, own)
        shutil.rmtree(own)
    return src.stem


def _forget(files: Files, own: Path) -> None:
    """The thumbnails of every file in the character's folder."""
    for p in own.rglob("*"):
        files._drop_thumbs(p)


def _fits(text: str, field: str) -> None:
    """No cap of the Hub's on the notes or the voice; only the size of the text a picture file holds
    (`pngtext.MAX`, file safety, as `named.set_text`)."""
    if len(text) > pngtext.MAX:
        raise Invalid(field, f"Text is at most {pngtext.MAX:,} characters")


def set_notes(files: Files, item_id: object, text: object) -> str:
    """`text` as the notes on a character, saved inside its file ("" clears them; `named.write_text`). -> the
    character's id (now .png)."""
    folder, src = _own(files, item_id)
    if not isinstance(text, str) or "\0" in text:
        raise Invalid("notes", "Send the notes as text")
    text = text.strip()
    _fits(text, "notes")
    return f"chars/{named.write_text(files, folder, src, text).name}"


def set_voice(files: Files, item_id: object, text: object) -> str:
    """The words for a character's voice, saved inside its file ("" clears them; the notes kept). -> the character's
    id (now .png)."""
    folder, src = _own(files, item_id)
    if not isinstance(text, str) or "\0" in text:
        raise Invalid("voice", "Send the voice as text")
    text = " ".join(text.split())
    _fits(text, "voice")
    return f"chars/{named.write_text(files, folder, src, text, pngtext.VOICE).name}"


def sample_of(files: Files, name: str) -> Path | None:
    """The real path of the voice sample of the character called `name` (any case), else None."""
    if "chars" not in files._real or not isinstance(name, str) or not name.strip():
        return None
    found = samples(root(files), name.strip())
    return found[0] if found else None


def keep_voice(files: Files, sound_id: object, name: object) -> str:
    """A sound from Sounds as the voice of the character called `name`: copied in as `<Name>.wav`, stripped,
    replacing the one it had. -> the character's id."""
    if not isinstance(sound_id, str) or files.kind(sound_id) != "sound":
        raise Invalid("id", "That is not a sound")
    src = files.existing_media(sound_id)
    folder = root(files)
    item_id = find(files, name) if isinstance(name, str) else None
    if item_id is None:
        raise Invalid("name", "No character has that name")
    _install(folder, Path(item_id).stem, src, "id", "That sound could not be read")
    return item_id


def put_sample(files: Files, item_id: object, src: Path) -> dict:
    """A recording (made a WAV by the browser) as the voice of the character `item_id`:
    at least 2 s (no most), kept as `<Name>.wav` like a sound from Sounds. -> {id, seconds}."""
    folder, pic = _own(files, item_id)
    try:
        seconds = sound.facts(src)["seconds"]
    except (OSError, ValueError):
        raise Invalid("sample", UNREAD) from None
    if seconds < MIN_SAMPLE:
        raise Invalid("sample", "A voice sample is at least 2 seconds")
    _install(folder, pic.stem, src, "sample", UNREAD)
    return {"id": f"chars/{pic.name}", "seconds": seconds}


def _install(folder: Path, stem: str, src: Path, field: str, unread: str) -> None:
    """`src` copied in as `<stem>.wav`, stripped to its sound, replacing every sample of that stem (any case)."""
    tmp = folder / f".{stem}.hub-voice"
    shutil.copyfile(src, tmp)
    try:
        sound.strip(tmp)
    except (OSError, ValueError):
        tmp.unlink(missing_ok=True)
        raise Invalid(field, unread) from None
    for p in samples(folder, stem):
        p.unlink(missing_ok=True)
    os.replace(tmp, folder / f"{stem}{SAMPLE}")
