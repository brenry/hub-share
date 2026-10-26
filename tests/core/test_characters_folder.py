"""A character's folder `<Name>/` (the character's sheet, orbit, bits and `casting.json`) beside the
character's picture. The character is still one: the listing, its views and `list_characters`' answer are the same
with the folder there as without it; a rename carries the folder with the `.wav` and views, a removal erases it."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from hub.core.api import Invalid
from hub.core.files import Files
from hub.modules.generate_image import cast
from tests.fakes.wav import tiny_wav


@pytest.fixture
def files(tmp_path: Path) -> Files:
    chars = tmp_path / "Characters"
    chars.mkdir()
    Image.new("RGB", (64, 64)).save(chars / "Character 8.png")
    Image.new("RGB", (64, 64)).save(chars / "Character 8.side.png")
    Image.new("RGB", (64, 64)).save(chars / "Character 11.png")
    (chars / "Character 8.wav").write_bytes(tiny_wav())
    return Files(tmp_path / "data", None, chars)


def sheet(files: Files, name: str = "Character 8", record: bool = True) -> Path:
    home = Path(files.roots["chars"]) / name
    (home / "sheet").mkdir(parents=True)
    (home / "bits").mkdir()
    Image.new("RGB", (32, 48)).save(home / "sheet" / "front.png")
    Image.new("RGB", (32, 48)).save(home / "bits" / "2.png")
    (home / "orbit.mp4").write_bytes(b"\0\0\0\x18ftypisom")
    if record:
        (home / "casting.json").write_text('{"version": 1}', encoding="utf-8")
    return home


def test_the_listing_is_as_before_with_the_characters_folder_there(files):
    before = files.characters()
    sheet(files)
    after = files.characters()
    assert [c["name"] for c in after] == ["Character 11", "Character 8"], "the folder is no character"
    assert after == before
    assert files.character_views("Character 8") == ["chars/Character 8.side.png"], "nothing in the folder is a view"


def test_list_characters_answer_is_unchanged(files):
    sheet(files)
    listed = cast.listing(SimpleNamespace(files=files))
    assert listed == [{"name": "Character 11"}, {"name": "Character 8", "sample": True, "views": 1}]


def test_rename_carries_the_folder_with_the_wav_and_views(files):
    sheet(files)
    chars = Path(files.roots["chars"])
    assert files.character_rename("chars/Character 8.png", "Character 15") == "chars/Character 15.png"
    assert sorted(p.name for p in chars.iterdir()) == ["Character 11.png", "Character 15", "Character 15.png",
                                                       "Character 15.side.png", "Character 15.wav"]
    assert (chars / "Character 15" / "sheet" / "front.png").is_file() and \
        (chars / "Character 15" / "casting.json").is_file()


def test_a_change_of_case_carries_the_folder(files):
    sheet(files)
    files.character_rename("chars/Character 8.png", "character 8")
    assert (Path(files.roots["chars"]) / "character 8" / "orbit.mp4").is_file()


def test_rename_onto_another_folder_is_refused_before_anything_moves(files):
    sheet(files)
    (Path(files.roots["chars"]) / "Character 4").mkdir()
    with pytest.raises(Invalid) as err:
        files.character_rename("chars/Character 8.png", "Character 4")
    assert err.value.text == "A folder called Character 4 is in Characters already"
    assert (Path(files.roots["chars"]) / "Character 8.png").is_file() and \
        (Path(files.roots["chars"]) / "Character 8").is_dir()


def test_a_character_without_a_folder_renames_as_before(files):
    assert files.character_rename("chars/Character 11.png", "Character 29") == "chars/Character 29.png"
    assert not (Path(files.roots["chars"]) / "Character 29").exists()


def test_remove_erases_the_folder(files):
    sheet(files)
    assert files.character_remove("chars/Character 8.png") == "Character 8"
    assert sorted(p.name for p in Path(files.roots["chars"]).iterdir()) == ["Character 11.png"]


def test_rename_onto_a_folder_is_refused_even_without_a_folder_of_its_own(files):
    (Path(files.roots["chars"]) / "Character 4").mkdir()
    with pytest.raises(Invalid) as err:
        files.character_rename("chars/Character 11.png", "character 4")
    assert err.value.text == "A folder called Character 4 is in Characters already"
    assert (Path(files.roots["chars"]) / "Character 11.png").is_file()
