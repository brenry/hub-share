"""A character's views, `<Name>.<view>.<ext>` beside the character's picture. Listed under the
character, not as characters; renamed and erased with the character; a dotted stem with no listed character before it
stays a character of its own."""
from __future__ import annotations

from pathlib import Path

import pytest

from hub.core.files import Files
from tests.core.test_characters import png


@pytest.fixture
def chars(tmp_path: Path) -> Path:
    folder = tmp_path / "Characters"
    folder.mkdir()
    return folder


@pytest.fixture
def files(tmp_path: Path, chars: Path) -> Files:
    return Files(tmp_path / "data", tmp_path / "Drive", chars)


def test_views_list_under_their_character_by_view(files: Files, chars: Path) -> None:
    for name in ("Character 7.png", "Character 7.side.png", "Character 7.body.jpg", "character 7.Headshot.png",
                 "Character.37.png", "Character.37.side.png"):
        png(chars / name)
    listed = files.characters()
    assert [c["name"] for c in listed] == ["Character 7", "Character.37"], "a view is not a character; a dotted name is"
    assert listed[0]["views"] == [{"id": "chars/Character 7.body.jpg", "view": "body"},
                                  {"id": "chars/character 7.Headshot.png", "view": "Headshot"},
                                  {"id": "chars/Character 7.side.png", "view": "side"}]
    assert listed[1]["views"] == [{"id": "chars/Character.37.side.png", "view": "side"}]
    assert files.character_views("character 7") == ["chars/Character 7.body.jpg", "chars/character 7.Headshot.png",
                                              "chars/Character 7.side.png"]
    assert files.character_views("Nobody") == []
    assert files.kind("chars/Character 7.side.png") == "image" and \
        files.existing_media("chars/Character 7.side.png").is_file()


def test_a_dotted_stem_with_no_character_before_it_is_a_character(files: Files, chars: Path) -> None:
    png(chars / "Character 7.side.png")
    assert [c["name"] for c in files.characters()] == ["Character 7.side"]
    png(chars / "Character 7.png")
    assert [c["name"] for c in files.characters()] == ["Character 7"], "once Character 7 is there, its view is its"


def test_rename_and_remove_carry_the_views(files: Files, chars: Path) -> None:
    for name in ("Character 7.png", "Character 7.side.png", "Character 7.body.png", "Character 11.png"):
        png(chars / name)
    new_id = files.character_rename("chars/Character 7.png", "Character 39")
    assert new_id == "chars/Character 39.png"
    assert sorted(p.name for p in chars.iterdir()) == ["Character 11.png", "Character 39.body.png", "Character 39.png",
                                                       "Character 39.side.png"]
    assert [v["view"] for v in files.characters()[1]["views"]] == ["body", "side"]
    assert files.character_remove("chars/Character 39.png") == "Character 39"
    assert sorted(p.name for p in chars.iterdir()) == ["Character 11.png"]
