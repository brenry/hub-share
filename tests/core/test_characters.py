"""Characters: the folder of named pictures. A character is one picture at the top of the folder, named by
its file stem; the Hub lists them, finds one by name (any case) and puts a picture in under a name — a copy with its
metadata cut out — replacing whatever picture had that name."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin

from hub.core.api import Invalid
from hub.core.characters import NO_FOLDER
from hub.core.files import Files

NO_VOICE = {"voice": "", "sample": False, "views": []}          # no voice in words, no voice sample


def png(path: Path, color: tuple[int, int, int] = (200, 10, 10), size: tuple[int, int] = (16, 12),
        text: str | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    info = None
    if text is not None:
        info = PngImagePlugin.PngInfo()
        info.add_text("prompt", text)
    Image.new("RGB", size, color).save(path, "PNG", pnginfo=info)
    return path


def jpeg_with_exif(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    ex = Image.Exif()
    ex[0x010F] = "A camera maker"
    ex[0x0131] = "Some phone software 1.2"
    Image.new("RGB", (20, 10), (10, 120, 30)).save(path, "JPEG", quality=95, exif=ex.tobytes())
    return path


def age(path: Path, seconds_ago: int) -> None:
    t = path.stat().st_mtime - seconds_ago
    os.utime(path, (t, t))


@pytest.fixture
def chars(tmp_path: Path) -> Path:
    folder = tmp_path / "Characters"
    folder.mkdir()
    return folder


@pytest.fixture
def files(tmp_path: Path, chars: Path) -> Files:
    return Files(tmp_path / "data", tmp_path / "Drive", chars)


def test_the_listing_is_the_top_level_pictures_by_name(files: Files, chars: Path) -> None:
    png(chars / "character 42.png")
    png(chars / "Character 28.JPG")
    png(chars / "character 25.webp")
    png(chars / ".hidden.png")
    (chars / "notes.txt").write_text("not a picture")
    (chars / "page.html").write_text("<script>")
    (chars / "folder.png").mkdir()
    png(chars / "sub" / "Deep.png")
    assert files.characters() == [{"name": "character 25", "id": "chars/character 25.webp", "notes": "", **NO_VOICE},
                                  {"name": "Character 28", "id": "chars/Character 28.JPG", "notes": "", **NO_VOICE},
                                  {"name": "character 42", "id": "chars/character 42.png", "notes": "", **NO_VOICE}], \
        "sorted without regard to case; hidden files, other files, folders and pictures below are not characters"
    assert files.roots["chars"] == chars


def test_a_name_held_by_two_files_is_the_newer_ones(files: Files, chars: Path) -> None:
    old = png(chars / "Character 42.png")
    age(old, 100)
    png(chars / "character 42.jpg")
    assert files.characters() == [{"name": "character 42", "id": "chars/character 42.jpg", "notes": "", **NO_VOICE}]
    assert files.character("CHARACTER 42") == "chars/character 42.jpg"
    age(chars / "character 42.jpg", 200)
    assert files.character("character 42") == "chars/Character 42.png", "now the .png is the newer one"


def test_find_is_case_insensitive(files: Files, chars: Path) -> None:
    png(chars / "Character 43.png")
    assert files.character("character 43") == "chars/Character 43.png"
    assert files.character("  CHARACTER 43 ") == "chars/Character 43.png", "spaces around the name do not count"
    assert files.character("Character") is None
    assert files.character("") is None


def test_put_a_new_character_copies_the_picture_in(files: Files, chars: Path) -> None:
    src = png(files.roots["out"] / "2026-10-12" / "hero.png", (1, 2, 3))
    assert files.character_put("Character 42", "out/2026-10-12/hero.png") == "chars/Character 42.png"
    assert src.is_file(), "a copy: the picture stays where it was"
    assert files.characters() == [{"name": "Character 42", "id": "chars/Character 42.png", "notes": "", **NO_VOICE}]
    with Image.open(chars / "Character 42.png") as im:
        assert im.getpixel((0, 0)) == (1, 2, 3)
    assert [p.name for p in chars.iterdir()] == ["Character 42.png"], "no temporary file left behind"


def test_put_from_the_drive_and_from_another_character(files: Files, chars: Path, tmp_path: Path) -> None:
    png(tmp_path / "Drive" / "people" / "character 32.png", (9, 9, 9))
    assert files.character_put("Character 32", "drive/people/character 32.png") == "chars/Character 32.png"
    assert files.character_put("Character 35", "chars/Character 32.png") == "chars/Character 35.png"
    assert [c["name"] for c in files.characters()] == ["Character 32", "Character 35"], \
        "copied under another name; both stay"


def test_put_replaces_every_picture_that_had_the_name(files: Files, chars: Path) -> None:
    png(chars / "character 42.PNG", (5, 5, 5))
    old_jpg = png(chars / "CHARACTER 42.jpeg", (6, 6, 6))
    age(old_jpg, 50)
    png(chars / "Character 28.png")
    png(files.roots["out"] / "d" / "new.png", (7, 7, 7))
    assert files.character_put("Character 42", "out/d/new.png") == "chars/Character 42.png"
    assert sorted(p.name for p in chars.iterdir()) == ["Character 28.png", "Character 42.png"], \
        "any extension, any case: the old pictures of that name are gone"
    with Image.open(chars / "Character 42.png") as im:
        assert im.getpixel((0, 0)) == (7, 7, 7)
    assert files.character("character 42") == "chars/Character 42.png"


def test_put_with_another_type_changes_the_extension(files: Files, chars: Path) -> None:
    png(chars / "Character 42.png")
    jpeg_with_exif(files.roots["out"] / "d" / "photo.JPG")
    assert files.character_put("Character 42", "out/d/photo.JPG") == "chars/Character 42.jpg"
    assert [p.name for p in chars.iterdir()] == ["Character 42.jpg"]


def test_put_of_a_character_onto_its_own_name_changes_nothing(files: Files, chars: Path) -> None:
    pic = png(chars / "Character 42.png", text="keep me as I am")
    before = (pic.read_bytes(), pic.stat().st_mtime_ns)
    assert files.character_put("character 42", "chars/Character 42.png") == "chars/Character 42.png"
    assert (pic.read_bytes(), pic.stat().st_mtime_ns) == before, "no copy, no clean: the file is untouched"
    assert [p.name for p in chars.iterdir()] == ["Character 42.png"]


def test_put_cuts_the_metadata_out(files: Files, chars: Path) -> None:
    png(files.roots["out"] / "d" / "said.png", text="a secret prompt about a grey cat")
    jpeg_with_exif(files.roots["out"] / "d" / "photo.jpg")
    files.character_put("Cat", "out/d/said.png")
    files.character_put("Phone", "out/d/photo.jpg")
    cat, phone = chars / "Cat.png", chars / "Phone.jpg"
    assert b"secret prompt" not in cat.read_bytes() and b"tEXt" not in cat.read_bytes()
    with Image.open(cat) as im:
        assert "prompt" not in im.info
    assert b"camera maker" not in phone.read_bytes() and b"phone software" not in phone.read_bytes()
    with Image.open(phone) as im:
        assert dict(im.getexif()) == {}
    assert b"secret prompt" in (files.roots["out"] / "d" / "said.png").read_bytes(), "the source is left as it was"


def test_put_refuses_a_bad_name_or_a_missing_picture(files: Files, chars: Path) -> None:
    png(files.roots["out"] / "d" / "a.png")
    for bad in ("a/b", "..", ".hidden", "", "  ", 7, None, "x\\y"):
        with pytest.raises(Invalid) as err:
            files.character_put(bad, "out/d/a.png")
        assert err.value.field == "name", bad
    with pytest.raises(Invalid) as err:
        files.character_put("Gone", "out/d/missing.png")
    assert err.value.text == "That image is no longer available"
    (files.roots["out"] / "d" / "page.html").write_text("<script>")
    with pytest.raises(Invalid):
        files.character_put("Page", "out/d/page.html")
    assert list(chars.iterdir()) == [], "nothing was written"


def test_no_folder_chosen_lists_nothing_and_refuses_a_put(tmp_path: Path) -> None:
    files = Files(tmp_path / "data")
    png(files.roots["out"] / "d" / "a.png")
    assert "chars" not in files.roots
    assert files.characters() == [] and files.character("anyone") is None
    with pytest.raises(Invalid) as err:
        files.character_put("Character 42", "out/d/a.png")
    assert (err.value.field, err.value.text) == ("characters", NO_FOLDER)
    assert NO_FOLDER == "Choose the Characters folder in Settings → Storage"


def test_set_characters_points_the_root_elsewhere_and_leaves_the_drive(tmp_path: Path, chars: Path) -> None:
    files = Files(tmp_path / "data", tmp_path / "Drive")
    assert "chars" not in files.roots
    png(chars / "Character 42.png")
    files.set_characters(chars)
    assert files.roots["chars"] == chars and files.roots["drive"] == tmp_path / "Drive"
    assert files.existing_image("chars/Character 42.png") == chars / "Character 42.png"
    files.set_drive(None)
    assert files.roots["chars"] == chars and "drive" not in files.roots, "each root is set on its own"
    files.set_characters(None)
    assert "chars" not in files.roots and files.characters() == []
    with pytest.raises(Invalid):
        files.existing_image("chars/Character 42.png")
