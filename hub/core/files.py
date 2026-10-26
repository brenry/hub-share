"""Media roots and item ids. Implements `api.Files`.

Item id = `<root>/<relative path>`: `out/...` (the Temp, where every picture the hub makes or takes in lands),
`clips/...` (every clip the engine makes, `<day>/<time>.mp4`; clips only, never a picture), `sounds/...` (every sound
the engine makes, `<day>/<time>.wav`, and the audience's, `audience/<kind>.wav`; sounds only), `drive/...`
(the one Media folder, `paths.drive`, once set; `drive.py` has its folder operations). A client never sends a root path.
Resolution refuses NUL, backslashes, absolute paths, empty, `.` and `..` segments, and anything whose real path leaves
the root (symlinks). Thumbnails are made in memory (`thumbs.py`); nothing about a picture is written anywhere.
"""
from __future__ import annotations

import os
import warnings
from pathlib import Path
from urllib.parse import quote

from PIL import Image

from hub.core import audience, characters, clean, clip, clipthumb, drive, named, sequences, sound, temp, thumbs
from hub.core.api import Invalid
from hub.core.roots import (  # noqa: F401  (re-exported: the roots' types, names and time paths)
    CLIP_TYPES,
    CLIPS,
    IMAGE_TYPES,
    MEDIA_TYPES,
    OWN,
    SCRIPTS,
    SETS,
    SOUND_TYPES,
    SOUNDS,
    forget_older_records,
    refuse_sets,
    temp_path,
)

THUMB_SIZES = (96, 336, 1024)
GONE = "That image is no longer available"

Image.MAX_IMAGE_PIXELS = thumbs.MAX_PIXELS
warnings.simplefilter("error", Image.DecompressionBombWarning)  # refuse, never print


class Files(sequences.SequenceFiles):
    def __init__(self, data_dir: Path, drive_root: Path | None = None, characters_root: Path | None = None) -> None:
        """Temp (`<data>/outputs`), the clips (`<data>/clips`) and the sounds (`<data>/sounds`) are the Hub's own,
        fixed and created here. The Drive and the Characters folder are set in Settings, used as they are and never
        created; until chosen, none."""
        self.data_dir = data_dir
        self.thumbs = thumbs.ThumbStore()
        for own in OWN:
            (data_dir / own).mkdir(parents=True, exist_ok=True)
        forget_older_records(data_dir)
        self._drive, self._chars = drive_root, characters_root
        self.storyboards: str | None = None     # a Drive folder whose storyboards' pictures hold text (`named`)
        self._build()

    def set_drive(self, drive_root: Path | None) -> None:
        """Point the Drive at another folder (None: no Drive). Nothing is moved; old Drive items stop resolving."""
        self._drive = drive_root
        self._build()

    def set_characters(self, characters_root: Path | None) -> None:
        """Point Characters at another folder (None: none). Nothing is moved."""
        self._chars = characters_root
        self._build()

    def set_storyboards(self, rel: str | None) -> None:
        self.storyboards = rel or None   # relative to the Drive (None: none, only Characters' pictures hold text)

    def _build(self) -> None:
        d = self.data_dir
        self.roots = {"out": d / "outputs", CLIPS: d / CLIPS, SOUNDS: d / SOUNDS, SCRIPTS: d / SCRIPTS, SETS: d / SETS}
        if self._drive is not None:
            self.roots["drive"] = Path(self._drive)
        if self._chars is not None:
            self.roots["chars"] = Path(self._chars)
        self._real = {k: Path(os.path.realpath(v)) for k, v in self.roots.items()}

    # ---------------------------------------------------------------- ids and paths
    def resolve(self, item_id: str) -> Path:
        if (not isinstance(item_id, str) or not 3 <= len(item_id) <= 512 or "\0" in item_id or "\\" in item_id
                or item_id.startswith("/")):
            raise Invalid("item", GONE)
        parts = item_id.split("/")
        if len(parts) < 2 or parts[0] not in self._real or any(p in ("", ".", "..") for p in parts):
            raise Invalid("item", GONE)
        root = self._real[parts[0]]
        path = Path(os.path.realpath(root.joinpath(*parts[1:])))
        if os.path.commonpath([root, path]) != str(root) or path == root:
            raise Invalid("item", GONE)
        return path

    def existing_image(self, item_id: str) -> Path:
        path = self.resolve(item_id)
        if self.kind(item_id) != "image" or not path.is_file():
            raise Invalid("item", GONE)
        return path

    def existing_media(self, item_id: str) -> Path:
        """A picture (any root but the clips and sounds), a clip or a sound (its own root only) that is there, else
        Invalid."""
        path = self.resolve(item_id)
        if self.kind(item_id) is None or not path.is_file():
            raise Invalid("item", GONE)
        return path

    def clip_facts(self, item_id: str) -> dict | None:
        """What a clip's boxes say ({w, h, fps, frames, seconds, audio}, `clip.facts`), or None when it is not a clip
        that is there or its boxes do not read."""
        try:
            return clip.facts(self.existing_media(item_id)) if self.kind(item_id) == "clip" else None
        except (Invalid, ValueError, OSError):
            return None

    def sound_facts(self, item_id: str) -> dict | None:
        """A sound's {seconds} (`sound.facts`), or None when it is not a sound that is there or does not read."""
        try:
            return sound.facts(self.existing_media(item_id)) if self.kind(item_id) == "sound" else None
        except (Invalid, ValueError, OSError):
            return None

    def item_for(self, path: Path) -> str | None:
        """The item id of a file inside a media root, else None."""
        real = Path(os.path.realpath(path))
        for name, root in self._real.items():
            if real != root and os.path.commonpath([root, real]) == str(root):
                return f"{name}/{real.relative_to(root).as_posix()}"
        return None

    def kind(self, item_id: str) -> str | None:
        """"clip" for an MP4 in the clips root, "sound" for a WAV in the sounds root, "image" for a picture anywhere
        else but the scripts root (no media), else None."""
        suffix, root = Path(item_id).suffix.lower(), item_id.split("/", 1)[0]
        own = {CLIPS: ("clip", CLIP_TYPES), SOUNDS: ("sound", SOUND_TYPES), SCRIPTS: (None, ())}
        kind, types = own.get(root, ("image", IMAGE_TYPES))
        return kind if suffix in types else None

    def _version(self, item_id: str) -> str:
        try:
            return f"?v={self.resolve(item_id).stat().st_mtime_ns}"
        except (Invalid, OSError):
            return ""

    def url(self, item_id: str) -> str:
        return f"/files/{quote(item_id, safe='/')}{self._version(item_id)}"

    def thumb_url(self, item_id: str, size: int = 336) -> str | None:
        if self.kind(item_id) == "sound":
            return None
        return f"/thumbs/{quote(item_id, safe='/')}/{size}{self._version(item_id)}"

    # ---------------------------------------------------------------- taking a picture in
    def take_in(self, tmp: Path, suffix: str) -> str:
        """Move a checked upload into Temp under a time name, its metadata cut out. -> its item id."""
        try:
            clean.strip(tmp)
        except (OSError, ValueError):
            raise Invalid("image", "That image could not be read") from None
        dest = temp_path(self.roots["out"], suffix)
        os.replace(tmp, dest)
        return f"out/{dest.relative_to(self.roots['out']).as_posix()}"

    def take_in_sound(self, tmp: Path) -> dict:
        """A checked WAV upload into the sounds root under a time name, only its sound kept. -> {id, seconds}."""
        try:
            sound.strip(tmp)
            seconds = sound.facts(tmp)["seconds"]
        except (OSError, ValueError, KeyError):
            raise Invalid("sound", "That sound file could not be read") from None
        dest = temp_path(self.roots[SOUNDS], ".wav")
        os.replace(tmp, dest)
        return {"id": f"{SOUNDS}/{dest.relative_to(self.roots[SOUNDS]).as_posix()}", "seconds": seconds}

    # ---------------------------------------------------------------- delete and move
    def _drop_thumbs(self, src: Path) -> None:
        self.thumbs.forget(f"{src}|")

    def delete(self, ids: list[str]) -> list[str]:
        """Erase Temp, clips, sounds and Drive files for good, at once, no trash. -> ids erased."""
        refuse_sets(ids)
        gone = []
        for item in ids:
            try:
                src = self.existing_media(item)
            except Invalid:
                continue
            self._drop_thumbs(src)
            src.unlink(missing_ok=True)
            gone.append(item)
        return gone

    def move(self, ids: list[str], to: str) -> list[tuple[str, str]]:
        """Move outputs or drive files into a drive folder (`to`, relative; "" is the root). A name already
        there is kept and the new file gets a numbered name. -> (old id, new id) for each file moved."""
        refuse_sets(ids)
        return drive.move_items(self, ids, to)

    def regroup(self, ids: list[str], group: str) -> list[tuple[str, str]]:
        return temp.regroup(self, ids, group)

    def file_clip(self, item_id: str, group: str, name: str) -> str:
        return temp.file_clip(self, item_id, group, name)

    def newest_temp(self) -> str | None:
        return temp.newest_temp(self)

    def file_sound(self, item_id: str, name: str) -> str:
        return audience.file_sound(self, item_id, name)

    def keep_audience(self, sound_id: str, kind: str) -> str:
        return audience.keep_audience(self, sound_id, kind)

    # ---------------------------------------------------------------- the Drive's folders
    def characters(self) -> list[dict]:
        return characters.listing(self)

    def character(self, name: str) -> str | None:
        return characters.find(self, name)

    def character_put(self, name: str, item_id: str) -> str:
        return self.put_picture("chars", name, item_id)

    def character_rename(self, item_id: str, name: str) -> str:
        return characters.rename(self, item_id, name)

    def put_picture(self, folder: str, name: str, src: str) -> str:
        return named.put(self, folder, name, src)

    def rename_picture(self, item_id: str, name: str) -> str:
        return named.rename(self, item_id, name)

    def picture_text(self, item_id: str) -> str:
        return named.read_text(self, item_id)

    def picture_text_set(self, item_id: str, text: str) -> str:
        return named.set_text(self, item_id, text)

    def character_remove(self, item_id: str) -> str:
        return characters.remove(self, item_id)

    def character_notes(self, item_id: str, text: str) -> str:
        return characters.set_notes(self, item_id, text)

    def character_voice(self, item_id: str, text: str) -> str:
        return characters.set_voice(self, item_id, text)

    def character_sample(self, name: str) -> Path | None:
        return characters.sample_of(self, name)

    def character_views(self, name: str) -> list[str]:
        """The ids of the character's view pictures, by view; [] without the folder or the character."""
        if "chars" not in self._real:
            return []
        return [f"chars/{p.name}" for p in characters.views(characters.root(self), name)]

    def keep_voice(self, sound_id: str, name: str) -> str:
        return characters.keep_voice(self, sound_id, name)

    def character_sample_put(self, item_id: str, src: Path) -> dict:
        return characters.put_sample(self, item_id, src)

    def folder_list(self, path: str) -> dict:
        return drive.listing(self, path)

    def folder_new(self, path: str, name: str) -> str:
        return drive.make(self, path, name)

    def folder_rename(self, path: str, name: str) -> str:
        return drive.rename(self, path, name)

    def folder_move(self, paths: list[str], to: str) -> list[str]:
        return drive.move(self, paths, to)

    def folder_remove(self, path: str) -> None:
        drive.remove(self, path)

    # ---------------------------------------------------------------- thumbnails
    def thumbnail(self, item_id: str, size: int) -> bytes:
        """WebP thumbnail from the in-memory store, made on first look. Runs in a worker thread."""
        if self.kind(item_id) == "sound":
            raise Invalid("item", "A sound has no thumbnail")
        if size not in THUMB_SIZES:
            raise Invalid("size", "Unknown thumbnail size")
        if self.kind(item_id) == "clip":                 # its first frame (`clipthumb`), kept in memory only
            src = self.existing_media(item_id)
            key = f"{src}|{src.stat().st_mtime_ns}|{size}"
            made = self.thumbs.get(key) or clipthumb.first_frame(src, size)
            if made is None:
                raise Invalid("item", "This clip gives no frame")
            self.thumbs.put(key, made)
            return made
        src = self.existing_image(item_id)
        return self.thumbs.make(f"{src}|{src.stat().st_mtime_ns}|{size}", src, size)
