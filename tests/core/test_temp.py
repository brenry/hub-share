"""The Hub's own roots (`hub/core/temp.py` through `Files`): a clip filed under a group with a name, and the newest
Temp picture by day folder and time name, whatever group it sits in."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from hub.core.api import Invalid
from hub.core.files import Files
from tests.core.test_characters import png

DAY = "2026-10-01"


@pytest.fixture
def files(tmp_path: Path) -> Files:
    return Files(tmp_path / "data")


def clip(files: Files, rel: str, at: float = 0.0) -> str:
    path = files.roots["clips"] / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0\0\0\x18ftypisom")
    if at:
        os.utime(path, (at, at))
    return f"clips/{rel}"


def picture(files: Files, rel: str) -> str:
    png(files.roots["out"] / rel)
    return f"out/{rel}"


def test_a_clip_is_filed_by_name_and_a_redo_gets_a_number(files: Files) -> None:
    """c1573bb, 1be310f: every clip in the clips root, named `<its mtime> - <group> <name>.mp4`."""
    at = time.mktime((2026, 10, 1, 10, 15, 0, 0, 0, -1))
    stamp = time.strftime("%Y-%m-%d %H%M%S", time.localtime(at))
    first = clip(files, f"{DAY}/101500-000.mp4", at)
    assert files.file_clip(first, "Trip", "01") == f"clips/{stamp} - Trip 01.mp4"
    assert not (files.roots["clips"] / DAY / "101500-000.mp4").exists()
    assert (files.roots["clips"] / f"{stamp} - Trip 01.mp4").is_file()
    assert files.file_clip(clip(files, f"{DAY}/101700-000.mp4", at), "Trip", "01") == f"clips/{stamp} - Trip 01-2.mp4"
    assert files.file_clip(clip(files, f"{DAY}/Other/101900-000.mp4", at), "Trip", "01") == \
        f"clips/{stamp} - Trip 01-3.mp4"
    assert files.file_clip(f"clips/{stamp} - Trip 01.mp4", "Trip", "01") == f"clips/{stamp} - Trip 01.mp4", \
        "already there"
    later = time.mktime((2026, 10, 2, 0, 1, 0, 0, 0, -1))
    named = time.strftime("%Y-%m-%d %H%M%S", time.localtime(later))
    assert files.file_clip(clip(files, "2026-10-02/000100-000.mp4", later), "Trip", "02") == \
        f"clips/{named} - Trip 02.mp4", "the time is the clip's own"


def test_a_picture_or_a_missing_clip_is_refused(files: Files) -> None:
    for item in (picture(files, f"{DAY}/a.png"), f"clips/{DAY}/a.png", "drive/a.mp4", "clips/a.mp4", None, 7):
        with pytest.raises(Invalid) as err:
            files.file_clip(item, "Trip", "01")  # type: ignore[arg-type]
        assert err.value.field == "item", item
    with pytest.raises(Invalid) as err:
        files.file_clip(f"clips/{DAY}/gone.mp4", "Trip", "01")
    assert err.value.text == "That image is no longer available"


@pytest.mark.parametrize(("group", "name", "field"), [("a/b", "01", "group"), (".hidden", "01", "group"),
                                                      ("..", "01", "group"), ("", "01", "group"),
                                                      ("Trip", "0/1", "name"), ("Trip", ".01", "name"),
                                                      ("Trip", 1, "name")])
def test_a_group_or_name_that_is_not_plain_is_refused(files: Files, group: object, name: object, field: str) -> None:
    item = clip(files, f"{DAY}/101500-000.mp4")
    with pytest.raises(Invalid) as err:
        files.file_clip(item, group, name)  # type: ignore[arg-type]
    assert err.value.field == field
    assert (files.roots["clips"] / DAY / "101500-000.mp4").is_file(), "nothing moved"


def test_empty_temp_gives_none(files: Files) -> None:
    assert files.newest_temp() is None
    (files.roots["out"] / DAY / "Favorites").mkdir(parents=True)
    clip(files, "2026-12-31/235959-999.mp4")
    assert files.newest_temp() is None, "empty folders and clips are not pictures"


def test_a_later_loose_picture_wins_over_an_earlier_favorite(files: Files) -> None:
    picture(files, f"{DAY}/Favorites/090000-000.png")
    loose = picture(files, f"{DAY}/100000-000.png")
    assert files.newest_temp() == loose
    late = picture(files, f"{DAY}/Favorites/110000-000.jpg")
    assert files.newest_temp() == late, "a group does not hide a later picture"
    again = picture(files, f"{DAY}/Favorites/110000-000-2.png")
    assert files.newest_temp() == again, "the second file of the same millisecond is the newer"


def test_a_later_day_wins_and_a_hidden_or_clip_file_is_skipped(files: Files) -> None:
    picture(files, f"{DAY}/235959-999.png")
    newest = picture(files, "2026-10-02/000001-000.png")
    picture(files, "2026-10-03/.120000-000.png")                       # half taken in
    picture(files, "2026-10-03/.tmp/120000-000.png")
    (files.roots["out"] / "2026-10-03" / "130000-000.mp4").write_bytes(b"x")
    clip(files, "2026-10-04/000000-000.mp4")
    assert files.newest_temp() == newest
