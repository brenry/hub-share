"""Characters renamed and deleted from the Media tree: the file is the record, so a rename renames the file and a
delete erases it; nothing of the old name is left in the folder or in the thumbnail store."""
from __future__ import annotations

from pathlib import Path

import pytest

from hub.core.api import Invalid
from hub.core.characters import NO_FOLDER
from hub.core.files import THUMB_SIZES, Files
from tests.core.test_characters import age, png

NO_VOICE = {"voice": "", "sample": False, "views": []}          # no voice in words, no voice sample


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


def thumbed(files: Files, item_id: str) -> bool:
    files.thumbnail(item_id, min(THUMB_SIZES))
    return any(k.startswith(str(files.existing_image(item_id))) for k in files.thumbs._items)


def test_rename_renames_the_file_and_keeps_its_type(files: Files, chars: Path) -> None:
    png(chars / "Character 42.png")
    assert thumbed(files, "chars/Character 42.png")
    keys_before = set(files.thumbs._items)
    assert files.character_rename("chars/Character 42.png", "  Character 32 ") == "chars/Character 32.png"
    assert names(chars) == ["Character 32.png"]
    assert files.characters() == [{"name": "Character 32", "id": "chars/Character 32.png", "notes": "", **NO_VOICE}]
    assert not set(files.thumbs._items) & keys_before, "the old name's thumbnails are gone"


def test_rename_changing_only_the_case(files: Files, chars: Path) -> None:
    png(chars / "character 42.png")
    assert files.character_rename("chars/character 42.png", "Character 42") == "chars/Character 42.png"
    assert names(chars) == ["Character 42.png"]


def test_rename_takes_an_older_file_of_the_old_name_with_it(files: Files, chars: Path) -> None:
    age(png(chars / "Character 42.jpg"), 100)
    png(chars / "Character 42.png")
    files.character_rename("chars/Character 42.png", "Character 32")
    assert names(chars) == ["Character 32.png"], "the old name does not come back with the older picture"


def test_rename_refuses_a_name_another_character_has(files: Files, chars: Path) -> None:
    png(chars / "Character 42.png")
    png(chars / "Character 28.png")
    with pytest.raises(Invalid) as e:
        files.character_rename("chars/Character 42.png", "character 28")
    assert (e.value.field, e.value.text) == ("name", "A character is already called character 28")
    assert names(chars) == ["Character 28.png", "Character 42.png"], "nothing changed"


@pytest.mark.parametrize("bad", ["", "  ", "a/b", "a\\b", ".hidden", None, 7])
def test_rename_refuses_a_name_that_is_not_a_plain_file_name(files: Files, chars: Path, bad: object) -> None:
    png(chars / "Character 42.png")
    with pytest.raises(Invalid):
        files.character_rename("chars/Character 42.png", bad)  # type: ignore[arg-type]
    assert names(chars) == ["Character 42.png"]


@pytest.mark.parametrize("bad", ["out/x.png", "drive/Character 42.png", "chars/../x.png", "chars/sub/x.png",
                                 "chars/Nobody.png", None])
def test_only_a_character_in_the_folder_can_be_renamed_or_deleted(files: Files, chars: Path, bad: object) -> None:
    png(chars / "Character 42.png")
    with pytest.raises(Invalid):
        files.character_rename(bad, "X")  # type: ignore[arg-type]
    with pytest.raises(Invalid):
        files.character_remove(bad)  # type: ignore[arg-type]
    assert names(chars) == ["Character 42.png"]


def test_delete_erases_the_file_and_every_file_of_that_name(files: Files, chars: Path) -> None:
    age(png(chars / "Character 42.jpg"), 100)
    png(chars / "Character 42.png")
    png(chars / "Character 28.png")
    assert thumbed(files, "chars/Character 42.png")
    assert files.character_remove("chars/Character 42.png") == "Character 42"
    assert names(chars) == ["Character 28.png"]
    assert not any("Character 42" in k for k in files.thumbs._items)
    assert files.characters() == [{"name": "Character 28", "id": "chars/Character 28.png", "notes": "", **NO_VOICE}]


def test_nothing_is_written_outside_the_folder(files: Files, chars: Path, tmp_path: Path) -> None:
    png(chars / "Character 42.png")
    before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.parent != chars)
    files.character_rename("chars/Character 42.png", "Character 32")
    files.character_remove("chars/Character 32.png")
    after = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.parent != chars)
    assert after == before and names(chars) == []


def test_no_folder_chosen(tmp_path: Path) -> None:
    files = Files(tmp_path / "data")
    for call in (lambda: files.character_rename("chars/A.png", "B"), lambda: files.character_remove("chars/A.png")):
        with pytest.raises(Invalid) as e:
            call()
        assert e.value.text == NO_FOLDER
