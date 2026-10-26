"""The notes on a character: one PNG text field inside the character's own file, nothing beside it. Saving
writes the file again as PNG pixel for pixel; the notes stay with the name through a rename and a new picture;
a picture coming in under a new name starts with none."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from hub.core.api import Invalid
from hub.core.characters import NOTES_KEY, notes_of
from hub.core.files import Files
from tests.core.test_characters import age, jpeg_with_exif, png

NO_VOICE = {"voice": "", "sample": False, "views": []}          # no voice in words, no voice sample

CHARACTER_30 = "Note 1; note 2; note 3."


@pytest.fixture
def chars(tmp_path: Path) -> Path:
    folder = tmp_path / "Characters"
    folder.mkdir()
    return folder


@pytest.fixture
def files(tmp_path: Path, chars: Path) -> Files:
    return Files(tmp_path / "data", tmp_path / "Drive", chars)


def names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def pixels(path: Path) -> bytes:
    with Image.open(path) as im:
        return im.convert("RGBA").tobytes()


def test_notes_are_saved_in_the_file_and_listed(files: Files, chars: Path) -> None:
    png(chars / "Character 30.png", text="an old prompt")
    before = pixels(chars / "Character 30.png")
    assert files.character_notes("chars/Character 30.png", f"  {CHARACTER_30}\n") == "chars/Character 30.png"
    assert names(chars) == ["Character 30.png"], "nothing beside the picture"
    assert notes_of(chars / "Character 30.png") == CHARACTER_30
    with Image.open(chars / "Character 30.png") as im:
        assert {k for k in im.info if isinstance(im.info[k], str)} == {NOTES_KEY}, "the notes are the only text"
    assert pixels(chars / "Character 30.png") == before
    assert files.characters() == [{"name": "Character 30", "id": "chars/Character 30.png", "notes": CHARACTER_30,
                                   **NO_VOICE}]


def test_a_jpeg_becomes_a_png_pixel_for_pixel(files: Files, chars: Path) -> None:
    jpeg_with_exif(chars / "Character 30.jpg")
    before = pixels(chars / "Character 30.jpg")
    assert files.character_notes("chars/Character 30.jpg", CHARACTER_30) == "chars/Character 30.png"
    assert names(chars) == ["Character 30.png"]
    assert pixels(chars / "Character 30.png") == before
    with Image.open(chars / "Character 30.png") as im:
        assert not im.getexif(), "the camera's EXIF is not carried over"


def test_empty_notes_clear_the_field(files: Files, chars: Path) -> None:
    png(chars / "Character 30.png")
    files.character_notes("chars/Character 30.png", CHARACTER_30)
    files.character_notes("chars/Character 30.png", "   ")
    assert notes_of(chars / "Character 30.png") == ""
    with Image.open(chars / "Character 30.png") as im:
        assert NOTES_KEY not in im.info


def test_notes_of_any_length_are_saved_whole(files: Files, chars: Path) -> None:
    png(chars / "Character 1.png")                               # no cap of the Hub's on the notes
    files.character_notes("chars/Character 1.png", "x" * 1001)
    assert notes_of(chars / "Character 1.png") == "x" * 1001


@pytest.mark.parametrize("bad", [None, 7, ["x"], "a\0b"])
def test_bad_notes_are_refused_and_nothing_changes(files: Files, chars: Path, bad: object) -> None:
    png(chars / "Character 30.png")
    raw = (chars / "Character 30.png").read_bytes()
    with pytest.raises(Invalid) as e:
        files.character_notes("chars/Character 30.png", bad)  # type: ignore[arg-type]
    assert e.value.field == "notes"
    assert (chars / "Character 30.png").read_bytes() == raw


def test_only_a_character_in_the_folder_takes_notes(files: Files, chars: Path) -> None:
    for bad in ("out/x.png", "drive/x.png", "chars/../x.png", "chars/Nobody.png"):
        with pytest.raises(Invalid):
            files.character_notes(bad, CHARACTER_30)


def test_the_notes_stay_with_the_name(files: Files, chars: Path, tmp_path: Path) -> None:
    png(chars / "Character 30.png")
    files.character_notes("chars/Character 30.png", CHARACTER_30)
    assert files.character_rename("chars/Character 30.png", "Character 27") == "chars/Character 27.png"
    assert notes_of(chars / "Character 27.png") == CHARACTER_30, "a rename keeps them"
    new = jpeg_with_exif(tmp_path / "Drive" / "headshot.jpg")
    assert files.character_put("character 27", "drive/headshot.jpg") == "chars/character 27.png"
    assert names(chars) == ["character 27.png"]
    assert notes_of(chars / "character 27.png") == CHARACTER_30, "a new picture under the name keeps them"
    assert pixels(chars / "character 27.png") == pixels(new)


def test_a_new_name_starts_with_no_notes(files: Files, chars: Path, tmp_path: Path) -> None:
    png(chars / "Character 30.png")
    files.character_notes("chars/Character 30.png", CHARACTER_30)
    assert files.character_put("Copy", "chars/Character 30.png") == "chars/Copy.png"
    assert notes_of(chars / "Copy.png") == "", "copied in: everything cut"
    png(tmp_path / "Drive" / "p.png", text="prompt words")
    files.character_put("Other", "drive/p.png")
    assert notes_of(chars / "Other.png") == ""


def test_notes_take_an_older_file_of_the_name_with_them(files: Files, chars: Path) -> None:
    age(png(chars / "Character 30.png"), 100)
    jpeg_with_exif(chars / "Character 30.jpg")
    assert files.character_notes("chars/Character 30.jpg", CHARACTER_30) == "chars/Character 30.png"
    assert names(chars) == ["Character 30.png"] and notes_of(chars / "Character 30.png") == CHARACTER_30


def test_nothing_is_written_outside_the_folder(files: Files, chars: Path, tmp_path: Path) -> None:
    png(chars / "Character 30.png")
    outside = sorted(str(p) for p in tmp_path.rglob("*") if chars not in p.parents)
    files.character_notes("chars/Character 30.png", CHARACTER_30)
    files.character_notes("chars/Character 30.png", "")
    assert sorted(str(p) for p in tmp_path.rglob("*") if chars not in p.parents) == outside
    assert names(chars) == ["Character 30.png"]
