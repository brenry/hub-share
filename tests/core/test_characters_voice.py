"""A character's voice: the words for it, a second PNG text field (`Voice`) beside the
character's notes in the character's own file, and the voice as a sound, `<Name>.wav` beside the picture, kept from
Sounds; both go with the character's name."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from hub.core import pngtext
from hub.core.api import Invalid
from hub.core.files import Files
from tests.core.test_characters import png
from tests.fakes.wav import SECRET, tiny_wav

SOUND = "sounds/2026-10-17/120000-000.wav"
CHARACTER_8 = "Voice 1."


@pytest.fixture
def chars(tmp_path: Path) -> Path:
    folder = tmp_path / "Characters"
    folder.mkdir()
    return folder


@pytest.fixture
def files(tmp_path: Path, chars: Path) -> Files:
    f = Files(tmp_path / "data", tmp_path / "Drive", chars)
    (f.roots["sounds"] / "2026-10-17").mkdir()
    f.resolve(SOUND).write_bytes(tiny_wav(4, tagged=True))
    return f


def names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def texts(path: Path) -> dict[str, str]:
    with Image.open(path) as im:
        return {k: v for k, v in im.info.items() if isinstance(v, str)}


def test_the_voice_is_a_second_field_and_the_notes_stay(files: Files, chars: Path) -> None:
    png(chars / "Character 8.png")
    files.character_notes("chars/Character 8.png", "Lives by the river.")
    assert files.character_voice("chars/Character 8.png", f"  {CHARACTER_8}\n ") == "chars/Character 8.png"
    assert texts(chars / "Character 8.png") == {"Description": "Lives by the river.", "Voice": CHARACTER_8}
    files.character_notes("chars/Character 8.png", "Lives in the hills.")
    assert texts(chars / "Character 8.png") == {"Description": "Lives in the hills.", "Voice": CHARACTER_8}, \
        "notes keep voice"
    assert files.characters() == [{"name": "Character 8", "id": "chars/Character 8.png", "notes": "Lives in the hills.",
                                   "voice": CHARACTER_8, "sample": False, "views": []}]
    files.character_voice("chars/Character 8.png", "")
    assert texts(chars / "Character 8.png") == {"Description": "Lives in the hills."}, "empty clears the voice only"
    assert names(chars) == ["Character 8.png"], "nothing beside the picture"


def test_a_voice_is_text_of_any_length(files: Files, chars: Path) -> None:
    png(chars / "Character 8.png")
    files.character_voice("chars/Character 8.png", "x" * 301)                  # no cap of the Hub's
    assert texts(chars / "Character 8.png") == {"Voice": "x" * 301}
    with pytest.raises(Invalid, match="Send the voice as text"):
        files.character_voice("chars/Character 8.png", 3)            # type: ignore[arg-type]
    with pytest.raises(Invalid):
        files.character_voice("out/2026-10-17/x.png", CHARACTER_8)


def test_a_new_picture_under_the_name_keeps_both_fields(files: Files, chars: Path) -> None:
    png(chars / "Character 8.png")
    files.character_notes("chars/Character 8.png", "By the river.")
    files.character_voice("chars/Character 8.png", CHARACTER_8)
    png(files.roots["out"] / "2026-10-17" / "new.png", (9, 9, 9))
    assert files.character_put("Character 8", "out/2026-10-17/new.png") == "chars/Character 8.png"
    assert pngtext.fields(chars / "Character 8.png") == {"Description": "By the river.", "Voice": CHARACTER_8}


def test_keep_voice_copies_the_sound_stripped_beside_the_picture(files: Files, chars: Path) -> None:
    png(chars / "Character 8.png")
    assert files.keep_voice(SOUND, "character 8") == "chars/Character 8.png"
    assert names(chars) == ["Character 8.png", "Character 8.wav"]
    assert (chars / "Character 8.wav").read_bytes() == tiny_wav(4) and \
        SECRET not in (chars / "Character 8.wav").read_bytes()
    assert files.resolve(SOUND).is_file(), "a copy: the sound stays in Sounds"
    assert files.characters()[0]["sample"] is True and \
        files.character_sample("CHARACTER 8") == chars / "Character 8.wav"
    files.resolve(SOUND).write_bytes(tiny_wav(6))
    files.keep_voice(SOUND, "Character 8")
    assert (chars / "Character 8.wav").read_bytes() == tiny_wav(6), "the new one replaces the old"
    assert names(chars) == ["Character 8.png", "Character 8.wav"]


def test_keep_voice_refuses_what_is_not_a_sound_or_not_a_character(files: Files, chars: Path) -> None:
    png(chars / "Character 8.png")
    png(files.roots["out"] / "2026-10-17" / "a.png")
    with pytest.raises(Invalid, match="That is not a sound"):
        files.keep_voice("out/2026-10-17/a.png", "Character 8")
    with pytest.raises(Invalid, match="No character has that name"):
        files.keep_voice(SOUND, "Nobody")
    files.resolve(SOUND).write_bytes(b"RIFF....WAVE")
    with pytest.raises(Invalid, match="could not be read"):
        files.keep_voice(SOUND, "Character 8")
    assert names(chars) == ["Character 8.png"], "nothing left behind"


def test_rename_carries_the_sample_and_remove_erases_it(files: Files, chars: Path) -> None:
    png(chars / "Character 8.png")
    files.keep_voice(SOUND, "Character 8")
    assert files.character_rename("chars/Character 8.png", "Character 34") == "chars/Character 34.png"
    assert names(chars) == ["Character 34.png", "Character 34.wav"] and files.character_sample("Character 8") is None
    assert files.character_remove("chars/Character 34.png") == "Character 34"
    assert names(chars) == []
