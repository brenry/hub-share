"""The Drive (the one Media folder, `paths.drive`): folder operations, moving files in from the Temp, purge-delete on
both."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from hub.core.api import Invalid
from hub.core.files import Files
from tests.core.test_files import png_bytes


@pytest.fixture
def files(tmp_path: Path) -> Files:
    (tmp_path / "Drive").mkdir()
    f = Files(tmp_path / "data", tmp_path / "Drive")
    (f.roots["out"] / "day").mkdir()
    (f.roots["out"] / "day" / "a.png").write_bytes(png_bytes())
    (f.roots["out"] / "day" / "b.png").write_bytes(png_bytes())
    (f.roots["drive"] / "portraits").mkdir()
    (f.roots["drive"] / "portraits" / "a.png").write_bytes(png_bytes())
    (f.roots["drive"] / "posters").mkdir()
    (f.roots["drive"] / ".hidden").mkdir()
    (tmp_path / "outside").mkdir()
    os.symlink(tmp_path / "outside", f.roots["drive"] / "escape")
    return f


def test_no_drive_until_the_owner_chooses_one(tmp_path: Path) -> None:
    f = Files(tmp_path / "data")
    assert set(f.roots) == {"out", "clips", "sounds", "scripts", "sets"}
    assert f.roots["out"] == tmp_path / "data" / "outputs"
    assert f.folder_list("") == {"path": "", "name": "", "dirs": [], "ids": [], "unset": True}
    for op in (lambda: f.folder_new("", "x"), lambda: f.move(["out/day/a.png"], ""), lambda: f.folder_remove("x")):
        with pytest.raises(Invalid):
            op()
    assert not (tmp_path / "data" / "archive").exists() and not (tmp_path / "data" / "drive").exists()


def test_the_drive_lists(files: Files, tmp_path: Path) -> None:
    assert files.roots["drive"] == tmp_path / "Drive"
    top = files.folder_list("")
    assert top["path"] == "" and top["dirs"] == ["escape", "portraits", "posters"] and top["ids"] == []
    assert files.folder_list("portraits")["ids"] == ["drive/portraits/a.png"]
    assert files.folder_list("/portraits/")["path"] == "portraits", "slashes around are forgiven"
    for bad in ("escape", "../", "portraits/../../", ".hidden", "nope", "a\\b"):
        with pytest.raises(Invalid):
            files.folder_list(bad)


def test_a_long_name_is_taken_while_its_bytes_fit_the_disk(files: Files) -> None:
    assert files.folder_new("", "x" * 121) == "x" * 121              # the disk's 255 bytes, no less
    assert files.folder_new("", "é" * 127) == "é" * 127                # 254 bytes
    for over in ("x" * 256, "é" * 128):                                # 256 bytes
        with pytest.raises(Invalid) as e:
            files.folder_new("", over)
        assert e.value.text == "Use a plain folder name, without slashes"


def test_make_rename_move_folders(files: Files) -> None:
    assert files.folder_new("", "Studies") == "Studies"
    assert files.folder_new("Studies", "2026") == "Studies/2026"
    with pytest.raises(Invalid):
        files.folder_new("", "Studies")
    for bad in ("", " ", ".dot", "a/b", "..", "x" * 256):
        with pytest.raises(Invalid):
            files.folder_new("", bad)
    assert files.folder_rename("Studies/2026", "Autumn") == "Studies/Autumn"
    with pytest.raises(Invalid):
        files.folder_rename("", "Root")
    assert files.folder_move(["Studies/Autumn"], "posters") == ["posters/Autumn"]
    assert files.folder_move(["posters/Autumn"], "posters") == ["posters/Autumn"], "already there: no change"
    with pytest.raises(Invalid):
        files.folder_move(["posters"], "posters/Autumn")
    with pytest.raises(Invalid):
        files.folder_move([""], "posters")
    assert sorted(files.folder_list("posters")["dirs"]) == ["Autumn"]
    with pytest.raises(Invalid) as e:
        files.folder_move([], "posters")
    assert e.value.text == "Send one or more folders"
    made = [files.folder_new("Studies", f"Folder {k}") for k in range(1, 102)]
    assert len(files.folder_move(made, "posters")) == 101, "no count of the Hub's"


def test_move_files_in_from_temp_and_between_folders(files: Files) -> None:
    files.thumbnail("out/day/a.png", 96)
    moved = files.move(["out/day/a.png", "out/day/missing.png", "nope/x.png"], "portraits")
    assert moved == [("out/day/a.png", "drive/portraits/a (2).png")], "a name already there is kept"
    assert not (files.roots["out"] / "day" / "a.png").exists() and not files.thumbs._items, "thumbnail gone too"
    assert files.existing_image("drive/portraits/a (2).png").is_file()
    assert files.move(["drive/portraits/a (2).png"], "") == [("drive/portraits/a (2).png", "drive/a (2).png")]
    assert files.move(["drive/a (2).png"], "") == [], "already there"
    with pytest.raises(Invalid):
        files.move(["out/day/b.png"], "escape")


def test_delete_purges_drive_files_and_folders(files: Files) -> None:
    files.thumbnail("drive/portraits/a.png", 96)
    gone = files.delete(["drive/portraits/a.png", "out/day/b.png", "nope/x.png"])
    assert gone == ["drive/portraits/a.png", "out/day/b.png"]
    assert not files.thumbs._items and not (files.roots["drive"] / "portraits" / "a.png").exists()
    (files.roots["drive"] / "posters" / "deep").mkdir()
    (files.roots["drive"] / "posters" / "deep" / "p.png").write_bytes(png_bytes())
    files.thumbnail("drive/posters/deep/p.png", 96)
    files.folder_remove("posters")
    assert not (files.roots["drive"] / "posters").exists() and not files.thumbs._items
    assert not list(files.data_dir.rglob("p.png")), "nothing kept anywhere"
    with pytest.raises(Invalid):
        files.folder_remove("")
    with pytest.raises(Invalid):
        files.folder_remove("escape")
    assert (files.data_dir.parent / "outside").is_dir(), "a link out of the archive is never followed"
