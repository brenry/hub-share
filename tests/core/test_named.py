"""Named pictures through `Files` (`hub/core/named.py`): the one PNG text field and the folders allowed to hold it
(the top of Characters; one level under the storyboards folder once `paths.storyboards` is set), putting a picture
in under a name, and renaming one."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PIL import Image

from hub.core import named, pngtext
from hub.core.api import Invalid
from hub.core.files import Files
from hub.settings import SettingsError, storyboards_folder, validate
from tests.core.test_characters import jpeg_with_exif, png
from tests.core.test_characters_edit import thumbed

TRIP = "Storyboards/Trip"
CELL = "A lighthouse at dusk.\nThe camera rises."


@pytest.fixture
def files(tmp_path: Path) -> Files:
    (tmp_path / "Drive").mkdir()
    (tmp_path / "Characters").mkdir()
    f = Files(tmp_path / "data", tmp_path / "Drive", tmp_path / "Characters")
    f.set_storyboards("Storyboards")
    return f


def pixels(path: Path) -> bytes:
    with Image.open(path) as im:
        return im.convert("RGBA").tobytes()


def drive(files: Files, rel: str) -> Path:
    return files.roots["drive"] / rel


def test_text_is_kept_pixel_for_pixel_through_files(files: Files) -> None:
    cell = png(drive(files, f"{TRIP}/01.png"), text="an old prompt")
    char = png(files.roots["chars"] / "Character 17.png")
    before = pixels(cell)
    assert files.picture_text_set(f"drive/{TRIP}/01.png", CELL) == f"drive/{TRIP}/01.png"
    assert files.picture_text(f"drive/{TRIP}/01.png") == CELL and pixels(cell) == before
    with Image.open(cell) as im:
        assert {k for k in im.info if isinstance(im.info[k], str)} == {pngtext.KEY}, "the text is the only text"
    assert files.picture_text_set("chars/Character 17.png", "Lives by the sea.") == "chars/Character 17.png"
    assert files.picture_text("chars/Character 17.png") == "Lives by the sea." == files.characters()[0]["notes"]
    assert files.picture_text_set("chars/Character 17.png", "") == "chars/Character 17.png" and pngtext.read(char) == ""


def test_a_jpeg_becomes_a_png_and_the_older_file_goes(files: Files) -> None:
    jpeg_with_exif(drive(files, f"{TRIP}/02.jpg"))
    before = pixels(drive(files, f"{TRIP}/02.jpg"))
    assert files.picture_text_set(f"drive/{TRIP}/02.jpg", CELL) == f"drive/{TRIP}/02.png"
    assert sorted(p.name for p in drive(files, TRIP).iterdir()) == ["02.png"]
    assert pixels(drive(files, f"{TRIP}/02.png")) == before


@pytest.mark.parametrize("item", ["out/2026-10-01/a.png", "clips/2026-10-01/a.mp4", "drive/Other/a.png",
                                  "drive/Storyboards/a.png", f"drive/{TRIP}/deep/a.png", "drive/a.png",
                                  "chars/sub/a.png", f"drive/{TRIP}/../a.png", "elsewhere/a.png", 7])
def test_a_write_outside_the_text_folders_is_refused_by_its_text(files: Files, item: object) -> None:
    if isinstance(item, str) and ".." not in item and not item.startswith("elsewhere"):
        root, _, rel = item.partition("/")
        target = files.roots[root] / rel
        png(target) if target.suffix == ".png" else target.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(Invalid) as err:
        files.picture_text_set(item, CELL)  # type: ignore[arg-type]
    assert (err.value.field, err.value.text) == ("id", named.NO_TEXT)
    assert files.picture_text(item) == ""  # type: ignore[arg-type]


def test_a_read_outside_the_text_folders_gives_nothing(files: Files) -> None:
    png(drive(files, "Other/a.png"))
    pngtext.write(drive(files, "Other/a.png"), "kept by hand")
    assert pngtext.read(drive(files, "Other/a.png")) == "kept by hand"
    assert files.picture_text("drive/Other/a.png") == "", "a Drive folder outside the storyboards folder"
    jpeg_with_exif(drive(files, f"{TRIP}/03.jpg"))
    assert files.picture_text(f"drive/{TRIP}/03.jpg") == "", "a JPEG holds none"
    drive(files, f"{TRIP}/04.png").write_bytes(b"not a picture")
    assert files.picture_text(f"drive/{TRIP}/04.png") == "", "an unreadable file holds none"
    assert files.picture_text(f"drive/{TRIP}/05.png") == "", "a file that is not there holds none"


@pytest.mark.parametrize("bad", [None, 7, ["x"], "a\0b", "x" * (pngtext.MAX + 1)])
def test_bad_text_is_refused_and_nothing_changes(files: Files, bad: object) -> None:
    cell = png(drive(files, f"{TRIP}/01.png"))
    raw = cell.read_bytes()
    with pytest.raises(Invalid) as err:
        files.picture_text_set(f"drive/{TRIP}/01.png", bad)  # type: ignore[arg-type]
    assert err.value.field == "text" and cell.read_bytes() == raw


def test_writing_text_drops_the_thumbnails(files: Files) -> None:
    png(drive(files, f"{TRIP}/01.png"))
    assert thumbed(files, f"drive/{TRIP}/01.png")
    files.picture_text_set(f"drive/{TRIP}/01.png", CELL)
    assert not any("01.png" in k for k in files.thumbs._items)


def test_a_temp_copy_has_its_text_cut(files: Files, tmp_path: Path) -> None:
    files.picture_text_set(files.character_put("Character 17", take(files, png(tmp_path / "in.png"))),
                           "Lives by the sea.")
    copy = tmp_path / "upload.png"
    shutil.copyfile(files.roots["chars"] / "Character 17.png", copy)
    out = files.take_in(copy, ".png")
    assert pngtext.read(files.existing_image(out)) == "" and files.picture_text("chars/Character 17.png") != ""


def take(files: Files, path: Path) -> str:
    return files.take_in(path, path.suffix)


def test_with_storyboards_unset_only_characters_hold_text(tmp_path: Path) -> None:
    files = Files(tmp_path / "data", tmp_path / "Drive", tmp_path / "Characters")
    png(drive(files, f"{TRIP}/01.png"))
    png(files.roots["chars"] / "Character 17.png")
    assert files.storyboards is None
    with pytest.raises(Invalid) as err:
        files.picture_text_set(f"drive/{TRIP}/01.png", CELL)
    assert err.value.text == named.NO_TEXT
    assert files.picture_text_set("chars/Character 17.png", "notes") == "chars/Character 17.png"
    files.set_storyboards("Storyboards")
    assert files.picture_text_set(f"drive/{TRIP}/01.png", CELL) == f"drive/{TRIP}/01.png"
    files.set_storyboards(None)
    assert files.picture_text(f"drive/{TRIP}/01.png") == ""


def test_the_storyboards_setting_is_a_folder_inside_the_drive() -> None:
    assert storyboards_folder(validate({})) is None and "storyboards" not in validate({})["paths"]
    assert storyboards_folder(validate({"paths": {"storyboards": "Films/Boards/"}})) == "Films/Boards"
    assert storyboards_folder(validate({"paths": {"storyboards": ""}})) is None
    for bad in ("/Films", "../x", ".hidden", "a/../b", "a//b", "a\\b", 7, None):
        with pytest.raises(SettingsError) as err:
            validate({"paths": {"storyboards": bad}})
        assert err.value.field == "paths.storyboards"


# ---------------------------------------------------------------- L2: put and rename
def test_a_put_into_a_storyboard_keeps_the_old_cells_text(files: Files, tmp_path: Path) -> None:
    png(drive(files, f"{TRIP}/01.png"))
    files.picture_text_set(f"drive/{TRIP}/01.png", CELL)
    new = take(files, jpeg_with_exif(tmp_path / "shot.jpg"))
    assert files.put_picture(f"drive/{TRIP}", "01", new) == f"drive/{TRIP}/01.png"
    assert sorted(p.name for p in drive(files, TRIP).iterdir()) == ["01.png"]
    assert files.picture_text(f"drive/{TRIP}/01.png") == CELL
    assert pixels(drive(files, f"{TRIP}/01.png")) == pixels(files.existing_image(new))


def test_a_put_into_a_plain_drive_folder_carries_no_text(files: Files, tmp_path: Path) -> None:
    png(drive(files, "Other/01.png"))
    pngtext.write(drive(files, "Other/01.png"), "kept by hand")
    new = take(files, png(tmp_path / "shot.png", text="a prompt"))
    assert files.put_picture("drive/Other", "01", new) == "drive/Other/01.png"
    assert pngtext.read(drive(files, "Other/01.png")) == ""
    with Image.open(drive(files, "Other/01.png")) as im:
        assert "prompt" not in im.info, "metadata cut"
    assert files.put_picture("drive", "Top", new) == "drive/Top.png", "the Drive itself is a folder too"


def test_a_put_from_or_into_a_place_outside_the_roots_is_refused(files: Files, tmp_path: Path) -> None:
    src = take(files, png(tmp_path / "shot.png"))
    for folder in ("out/2026-10-01", "clips", "drive/../x", "drive/Missing", "chars/sub", "", None):
        with pytest.raises(Invalid):
            files.put_picture(folder, "01", src)  # type: ignore[arg-type]
    png(tmp_path / "elsewhere.png")
    for item in ("../elsewhere.png", "elsewhere/x.png", "drive/../../elsewhere.png"):
        with pytest.raises(Invalid):
            files.put_picture(f"drive/{TRIP}", "01", item)
    assert not drive(files, TRIP).exists()


@pytest.mark.parametrize("bad", ["..", ".hidden", "a/b", "", 7])
def test_a_bad_name_is_refused(files: Files, tmp_path: Path, bad: object) -> None:
    src = take(files, png(tmp_path / "shot.png"))
    png(drive(files, f"{TRIP}/01.png"))
    with pytest.raises(Invalid) as err:
        files.put_picture(f"drive/{TRIP}", bad, src)  # type: ignore[arg-type]
    assert err.value.field == "name"
    with pytest.raises(Invalid) as err:
        files.rename_picture(f"drive/{TRIP}/01.png", bad)  # type: ignore[arg-type]
    assert err.value.field == "name"
    assert sorted(p.name for p in drive(files, TRIP).iterdir()) == ["01.png"]


def test_a_rename_keeps_type_and_text_and_refuses_a_taken_stem(files: Files) -> None:
    png(drive(files, f"{TRIP}/01.png"))
    jpeg_with_exif(drive(files, f"{TRIP}/02.jpg"))
    files.picture_text_set(f"drive/{TRIP}/01.png", CELL)
    with pytest.raises(Invalid) as err:
        files.rename_picture(f"drive/{TRIP}/01.png", "02")
    assert (err.value.field, err.value.text) == ("name", named.TAKEN.format("02"))
    assert files.rename_picture(f"drive/{TRIP}/02.jpg", "03") == f"drive/{TRIP}/03.jpg"
    assert files.rename_picture(f"drive/{TRIP}/01.png", "02") == f"drive/{TRIP}/02.png"
    assert files.picture_text(f"drive/{TRIP}/02.png") == CELL
    assert sorted(p.name for p in drive(files, TRIP).iterdir()) == ["02.png", "03.jpg"]
    for item in ("out/2026-10-01/a.png", f"drive/{TRIP}/missing.png", f"drive/{TRIP}/../x.png"):
        with pytest.raises(Invalid):
            files.rename_picture(item, "x")
