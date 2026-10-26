"""The sequence files (`hub/core/sequences.py` through the `Files` delegates): one small JSON file per sequence beside
the clips, holding two tracks of item ids, order, in and out points and where track 2's items start; a
compare-and-swap on the revision; gone items dropped on read and skipped in the listing; every refusal one plain
line."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hub.core.api import Invalid
from hub.core.files import Files
from tests.engine.sequence_kit import DAY, clip, seq_path, two, whole


@pytest.fixture
def files(tmp_path: Path) -> Files:
    return Files(tmp_path / "data")


def listed(files: Files) -> list[dict]:
    """The listing without its times."""
    return [{k: v for k, v in x.items() if k != "changed"} for x in files.sequences()]


def refused(fn, *args) -> str:  # type: ignore[no-untyped-def]
    with pytest.raises(Invalid) as e:
        fn(*args)
    return e.value.text


def test_new_save_rename_delete_and_the_exact_bytes(files: Files) -> None:
    a, b = clip(files, "101500-123"), clip(files, "101600-456", frames=48, fps=16, audio=True)
    assert files.sequences() == []
    assert files.sequence_new("Film") == {"name": "Film", "revision": 0, "tracks": [[], []], "dropped": 0}
    path = seq_path(files, "Film")
    assert json.loads(path.read_text()) == {"version": 2, "revision": 0, "tracks": [[], []]}
    video = [{"clip": a, "in": 0, "out": 124}, {"clip": b, "in": 8, "out": 40}]
    saved = files.sequence_save("Film", two(video), 0, 200)
    assert saved == {"name": "Film", "revision": 1, "tracks": [video, []], "dropped": 0}
    value = {"version": 2, "revision": 1, "tracks": [video, []]}
    assert path.read_bytes() == json.dumps(value, indent=1, ensure_ascii=False).encode("utf-8")
    assert list(json.loads(path.read_text())) == ["version", "revision", "tracks"], "key order as written"
    assert files.sequence("Film") == {**saved, "dropped": 0}
    listed = files.sequences()
    assert [{k: v for k, v in x.items() if k != "changed"} for x in listed] == \
        [{"name": "Film", "clips": 2, "seconds": round(124 / 24 + 32 / 16, 2)}]
    assert listed[0]["changed"] == path.stat().st_mtime
    assert files.sequence_rename("Film", " Trailer ") == {"name": "Trailer", "revision": 1}
    assert not path.exists() and files.sequence("Trailer")["tracks"] == [video, []]
    assert files.sequence_rename("Trailer", "Trailer") == {"name": "Trailer", "revision": 1}
    files.sequence_delete("Trailer")
    assert files.sequences() == [] and not seq_path(files, "Trailer").exists()
    assert files.clip_facts(a) is not None and files.clip_facts(b) is not None, "a delete never touches a clip"


def test_the_listing_is_by_name_skips_gone_clips_and_never_rewrites(files: Files) -> None:
    a, b = clip(files, "101500-123"), clip(files, "101600-456")
    for name in ("b-roll", "Alpha"):
        files.sequence_new(name)
    files.sequence_save("Alpha", two([whole(a), {"clip": b, "in": 0, "out": 24}]), 0, 200)
    before = seq_path(files, "Alpha").read_bytes()
    files.resolve(b).unlink()
    assert listed(files) == [{"name": "Alpha", "clips": 1, "seconds": 5.17},
                             {"name": "b-roll", "clips": 0, "seconds": 0}]
    assert seq_path(files, "Alpha").read_bytes() == before, "the listing never rewrites"


def test_a_gone_clip_is_dropped_on_read_and_the_file_written_again(files: Files) -> None:
    a, b = clip(files, "101500-123"), clip(files, "101600-456")
    files.sequence_new("Film")
    files.sequence_save("Film", two([whole(a), whole(b)]), 0, 200)
    files.resolve(a).unlink()
    got = files.sequence("Film")
    assert (got["revision"], got["tracks"], got["dropped"]) == (2, [[whole(b)], []], 1)
    assert json.loads(seq_path(files, "Film").read_text())["revision"] == 2
    assert files.sequence("Film")["dropped"] == 0, "dropped once"
    files.resolve(b).write_bytes(b"\0\0\0\x08free")
    assert files.sequence("Film")["dropped"] == 1, "a clip whose boxes no longer read is gone too"


def test_no_sequences_folder_lists_nothing_and_a_torn_temp_file_is_erased_at_start(tmp_path: Path) -> None:
    files = Files(tmp_path / "data")
    assert files.sequences() == [] and not (files.roots["clips"] / "sequences").exists()
    files.sequence_new("Film")
    torn = seq_path(files, "Film").parent / ".Film.json.k2j3h4.tmp"
    torn.write_text("{half")
    assert listed(files) == [{"name": "Film", "clips": 0, "seconds": 0}], "a hidden file is no sequence"
    Files(tmp_path / "data")
    assert not torn.exists() and seq_path(files, "Film").exists()


def test_the_folder_is_no_media(files: Files) -> None:
    files.sequence_new("Film")
    item = "clips/sequences/Film.json"
    assert files.kind(item) is None and files.clip_facts(item) is None
    assert refused(files.existing_media, item) == "That image is no longer available"


def test_stale_revisions_are_refused(files: Files) -> None:
    a = clip(files, "101500-123")
    files.sequence_new("Film")
    files.sequence_save("Film", two([whole(a)]), 0, 200)
    assert refused(files.sequence_save, "Film", two([]), 0, 200) == "The sequence changed in another window", \
        "two saves from one revision: the second is refused"
    assert refused(files.sequence_save, "Film", two([]), 7, 200) == "The sequence changed in another window"
    assert refused(files.sequence_save, "Film", two([]), "1", 200) == "The sequence changed in another window"
    assert files.sequence_save("Film", two([]), 1, 200)["revision"] == 2


def test_every_store_refusal_by_its_line(files: Files) -> None:
    a = clip(files, "101500-123")
    picture = f"out/{DAY}/101500-123.png"
    files.sequence_new("Film")
    for bad in ("", "  ", None, 5):
        assert refused(files.sequence_new, bad) == "Name the sequence"
        assert refused(files.sequence, bad) == "Name the sequence"
    for bad in ("a/b", ".hidden", "x" * 256, "a\\b"):
        assert refused(files.sequence_new, bad) == "Use a plain sequence name, without slashes"
    assert refused(files.sequence_new, "Film") == "A sequence named Film already exists"
    files.sequence_new("Other")
    assert refused(files.sequence_rename, "Other", "Film") == "A sequence named Film already exists"
    for fn, args in ((files.sequence, ("Nope",)), (files.sequence_save, ("Nope", two([]), 0, 200)),
                     (files.sequence_rename, ("Nope", "New")), (files.sequence_delete, ("Nope",))):
        assert refused(fn, *args) == "There is no sequence named Nope"
    save = files.sequence_save
    assert refused(save, "Film", two([whole(a)] * 3), 0, 2) == "A track holds at most 2 items"
    assert refused(save, "Film", two([], [{**whole(a), "at": 0}] * 3), 0, 2) == "A track holds at most 2 items"
    only_media = "Only clips and sounds go in a sequence"
    assert refused(save, "Film", two([whole(picture)]), 0, 200) == only_media
    assert refused(save, "Film", two([whole("clips/sequences/Other.json")]), 0, 200) == only_media
    assert refused(save, "Film", two([{"sound": a, "in": 0, "out": 5}]), 0, 200) == only_media
    assert refused(save, "Film", two([{"in": 0, "out": 5}]), 0, 200) == only_media
    assert refused(save, "Film", two([whole(f"clips/{DAY}/nothing.mp4")]), 0, 200) == "That clip is gone"
    for start, end in ((0, 125), (-1, 10), (0, 1.5), (0, "124"), (True, 10)):
        assert refused(save, "Film", two([{"clip": a, "in": start, "out": end}]), 0, 200) == \
            "In and out are frames of the clip, from 0 to 124"
    for start, end in ((10, 10), (20, 10), (124, 124)):
        assert refused(save, "Film", two([{"clip": a, "in": start, "out": end}]), 0, 200) == \
            "A clip keeps at least one frame"
    only = ("A sequence holds item ids, order, in and out points, where track 2's items start and their level, "
            "fades and duck only")
    for extra in ({"prompt": "a fox"}, {"model": "any"}, {"at": 0}, {"gain_db": 0}):
        assert refused(save, "Film", two([{**whole(a), **extra}]), 0, 200) == only
    for at in (-1, 1.5, "0", None):
        assert refused(save, "Film", two([], [{**whole(a), "at": at}]), 0, 200) == only
    assert refused(save, "Film", two([{**whole(a), "level": 0.5}]), 0, 200) == only, "track 1 takes no level"
    bad_keys = "Level is 0 to 2, fades are milliseconds, duck is on or off"
    for extra in ({"level": 2.5}, {"level": -0.1}, {"level": "1"}, {"level": True}, {"fade_in": -1}, {"fade_in": 0.5},
                  {"fade_out": "500"}, {"duck": 1}, {"duck": "yes"}):
        assert refused(save, "Film", two([], [{**whole(a), "at": 0, **extra}]), 0, 200) == bad_keys, extra
    for bad in ("clips", [[]], [[], [], []], [[], "x"], None):
        assert refused(save, "Film", bad, 0, 200) == "A sequence has two tracks"
    assert files.sequence("Film")["revision"] == 0, "nothing refused was written"


@pytest.mark.parametrize("text", [
    "{half",
    "[]",
    json.dumps({"version": 1, "revision": 0, "video": [], "audio": [], "prompt": "a fox"}),
    json.dumps({"version": 1, "revision": 0, "video": [{"clip": "c", "in": 0, "out": 5, "model": "x"}], "audio": []}),
    json.dumps({"version": 2, "revision": 0, "video": [], "audio": []}),
    json.dumps({"version": 1, "revision": -1, "video": [], "audio": []}),
    json.dumps({"version": 1, "revision": 0, "video": [{"clip": "c", "in": 5, "out": 5}], "audio": []}),
    json.dumps({"version": 1, "revision": 0, "video": [], "audio": [{"sound": "s"}]}),
    json.dumps({"version": 1, "revision": 0, "video": [{"sound": "s", "in": 0, "out": 5}], "audio": []}),
    json.dumps({"version": 1, "revision": 0, "video": []}),
    json.dumps({"version": 3, "revision": 0, "tracks": [[], []]}),
    json.dumps({"version": 2, "revision": 0, "tracks": [[]]}),
    json.dumps({"version": 2, "revision": 0, "tracks": [[], [], []]}),
    json.dumps({"version": 2, "revision": 0, "tracks": [[], []], "prompt": "a fox"}),
    json.dumps({"version": 2, "revision": 0, "tracks": [[{"clip": "c", "in": 0, "out": 5, "at": 0}], []]}),
    json.dumps({"version": 2, "revision": 0, "tracks": [[], [{"clip": "c", "in": 0, "out": 5}]]}),
    json.dumps({"version": 2, "revision": 0, "tracks": [[], [{"sound": "s", "in": 0, "out": 5, "at": -1}]]}),
    json.dumps({"version": 2, "revision": 0, "tracks": [[{"clip": "c", "sound": "s", "in": 0, "out": 5}], []]}),
])
def test_a_file_off_the_shape_cannot_be_read(files: Files, text: str) -> None:
    path = seq_path(files, "Film")
    path.parent.mkdir(parents=True)
    path.write_text(text)
    assert refused(files.sequence, "Film") == "The sequence Film cannot be read"
    assert refused(files.sequence_save, "Film", two([]), 0, 200) == "The sequence Film cannot be read"
    assert listed(files) == [{"name": "Film", "clips": 0, "seconds": 0}], "listed, so it can be deleted"
    files.sequence_delete("Film")
    assert not path.exists()


def test_an_item_without_out_is_the_whole_clip_written_out(files: Files) -> None:
    a, b = clip(files, "101500-123"), clip(files, "101600-456", frames=48, fps=16)
    files.sequence_new("Film")
    saved = files.sequence_save("Film", two([{"clip": a, "in": 12}, {"clip": b, "in": 0, "out": None}]), 0, 200)
    video = [{"clip": a, "in": 12, "out": 124}, whole(b, 48)]
    assert (saved["revision"], saved["tracks"]) == (1, [video, []]), "one save, one revision"
    assert json.loads(seq_path(files, "Film").read_text())["tracks"][0] == video, "the file holds the frames"
    assert refused(files.sequence_save, "Film", two([{"clip": a, "in": 124}]), 1, 200) == \
        "A clip keeps at least one frame"


def test_a_name_whose_file_would_not_fit_the_disk_is_refused(files: Files) -> None:
    plain = "Use a plain sequence name, without slashes"
    for bad in ("é" * 119, "😀" * 60, "a\ud800b"):
        assert len(bad) <= 120
        assert refused(files.sequence_new, bad) == plain
    fits = "é" * 118                       # 236 bytes: `.<name>.json.<8>.tmp` is 255
    assert files.sequence_new(fits)["name"] == fits and seq_path(files, fits).is_file()
    assert refused(files.sequence_rename, fits, fits + "x") == plain


def test_a_rename_moves_nothing_it_refuses(files: Files) -> None:
    files.sequence_new("Film")
    for bad in ("", None, "a/b", ".hidden", "x" * 256, "😀" * 60):
        assert refused(files.sequence_rename, "Film", bad) in ("Name the sequence",
                                                              "Use a plain sequence name, without slashes")
    assert [p.name for p in seq_path(files, "Film").parent.iterdir()] == ["Film.json"]
    seq_path(files, "Torn").write_text("{half")
    assert refused(files.sequence_rename, "Torn", "Whole") == "The sequence Torn cannot be read"
    assert seq_path(files, "Torn").is_file() and not seq_path(files, "Whole").exists(), "an unreadable file stays"
