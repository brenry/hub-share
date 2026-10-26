"""The sequence file, version 2: a version 1 file reads as track 1 and is written as version 2 on its next save; sounds
on either track (in and out in milliseconds); track 1 holds clips or sounds, not both; track 2's items carry `at`;
a gone sound drops as a gone clip does; the length a saved file would have; a WAV upload kept in Sounds."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hub.core.api import Invalid
from hub.core.files import Files
from tests.engine.sequence_kit import clip, seq_path, sound, two, whole
from tests.fakes.wav import tiny_wav


@pytest.fixture
def files(tmp_path: Path) -> Files:
    return Files(tmp_path / "data")


def refused(fn, *args) -> str:  # type: ignore[no-untyped-def]
    with pytest.raises(Invalid) as e:
        fn(*args)
    return e.value.text


def test_a_stage_11_file_reads_as_track_1_and_saves_as_version_2(files: Files) -> None:
    a = clip(files, "101500-123")
    path = seq_path(files, "Old")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"version": 1, "revision": 4, "video": [whole(a)], "audio": []}))
    assert files.sequence("Old") == {"name": "Old", "revision": 4, "tracks": [[whole(a)], []], "dropped": 0}
    assert json.loads(path.read_text())["version"] == 1, "a read alone does not rewrite"
    files.sequence_save("Old", two([whole(a)]), 4, 200)
    assert json.loads(path.read_text()) == {"version": 2, "revision": 5, "tracks": [[whole(a)], []]}


def test_sounds_go_on_either_track_in_milliseconds(files: Files) -> None:
    a, s = clip(files, "101500-123"), sound(files, "120000-001", seconds=20.0)
    files.sequence_new("Voice")
    saved = files.sequence_save("Voice", two([{"sound": s, "in": 1000}], [{"clip": a, "in": 0, "out": 24, "at": 500}]),
                                0, 200)
    assert saved["tracks"] == [[{"sound": s, "in": 1000, "out": 20000}],
                               [{"clip": a, "in": 0, "out": 24, "at": 500}]], "no out: the sound's length"
    assert list(saved["tracks"][1][0]) == ["clip", "in", "out", "at"], "key order as written"
    assert [x["seconds"] for x in files.sequences()] == [19.0], "the length is track 1's"
    assert files.item_facts({"sound": s, "in": 0, "out": 5}) == {
        "kind": "sound", "id": s, "fps": 1000.0, "frames": 20000, "seconds": 20.0, "w": 0, "h": 0, "audio": True}


def test_with_track_1_empty_the_length_ends_with_track_2(files: Files) -> None:
    s = sound(files, "120000-001", seconds=4.0)
    files.sequence_new("Fx")
    files.sequence_save("Fx", two([], [{"sound": s, "in": 0, "out": 1500, "at": 3000},
                                      {"sound": s, "in": 0, "out": 500, "at": 0}]), 0, 200)
    assert [(x["clips"], x["seconds"]) for x in files.sequences()] == [(2, 4.5)]


def test_track_1_holds_clips_or_sounds_not_both(files: Files) -> None:
    a, s = clip(files, "101500-123"), sound(files, "120000-001")
    files.sequence_new("Mixed")
    assert refused(files.sequence_save, "Mixed", two([whole(a), {"sound": s, "in": 0}]), 0, 200) == \
        "Track 1 holds clips or sounds, not both"
    saved = files.sequence_save("Mixed", two([whole(a)], [{"sound": s, "in": 0, "at": 0}, {**whole(a), "at": 9}]),
                                0, 200)
    assert saved["revision"] == 1, "track 2 may hold both"


def test_sound_refusals_by_their_lines(files: Files) -> None:
    s = sound(files, "120000-001", seconds=2.0)
    files.sequence_new("Voice")
    save = files.sequence_save
    for start, end in ((0, 2001), (-1, 10), (0, 1.5)):
        assert refused(save, "Voice", two([{"sound": s, "in": start, "out": end}]), 0, 200) == \
            "In and out are milliseconds of the sound, from 0 to 2000"
    assert refused(save, "Voice", two([{"sound": s, "in": 10, "out": 10}]), 0, 200) == \
        "A sound keeps at least one millisecond"
    assert refused(save, "Voice", two([{"sound": "sounds/2026-10-14/none.wav", "in": 0}]), 0, 200) == \
        "That sound is gone"
    assert refused(save, "Voice", two([{"clip": s, "in": 0}]), 0, 200) == "Only clips and sounds go in a sequence"


def test_a_gone_sound_drops_on_read(files: Files) -> None:
    s, t = sound(files, "120000-001"), sound(files, "120000-002")
    files.sequence_new("Voice")
    files.sequence_save("Voice", two([{"sound": s, "in": 0}], [{"sound": t, "in": 0, "at": 0}]), 0, 200)
    files.resolve(t).unlink()
    got = files.sequence("Voice")
    assert (got["revision"], len(got["tracks"][1]), got["dropped"]) == (2, 0, 1)


def test_a_wav_upload_lands_in_sounds_with_only_its_sound(files: Files) -> None:
    tmp = files.roots["out"] / ".up-x"
    tmp.write_bytes(tiny_wav(seconds=3.0, rate=48_000, tagged=True))
    made = files.take_in_sound(tmp)
    assert made["seconds"] == 3.0 and made["id"].startswith("sounds/") and files.kind(made["id"]) == "sound"
    assert b"LIST" not in files.resolve(made["id"]).read_bytes() and not tmp.exists()
    bad = files.roots["out"] / ".up-y"
    bad.write_bytes(b"not a sound")
    assert refused(files.take_in_sound, bad) == "That sound file could not be read"


def test_a_beds_keys_read_and_a_file_with_a_bad_one_does_not(files: Files) -> None:
    """`level`, `fade_in`, `fade_out`, `duck` are track 2's optional keys; a file without them reads
    with none; a file with a malformed one or with one on track 1 is not a sequence file."""
    from hub.core import seqshape

    s = sound(files, "120000-001")
    bed = {"sound": s, "in": 0, "out": 1000, "at": 0, "level": 0.5, "fade_in": 1000, "fade_out": 500, "duck": True}
    old = {"version": 2, "revision": 3, "tracks": [[], [{"sound": s, "in": 0, "out": 1000, "at": 0}]]}
    assert seqshape.read_shape({**old, "tracks": [[], [bed]]}) == [[], [bed]]
    assert seqshape.read_shape(old) == old["tracks"], "a file from before 022 reads as it did"
    assert seqshape.read_shape({**old, "tracks": [[], [{**bed, "level": 0}]]}) is not None, "silent is a level"
    for bad in ({"level": 2.5}, {"level": "1"}, {"level": True}, {"fade_in": -1}, {"fade_out": 1.5}, {"duck": 1},
                {"duck": "on"}, {"gain": 1}):
        assert seqshape.read_shape({**old, "tracks": [[], [{**bed, **bad}]]}) is None, bad
    on_track_1 = {"version": 2, "revision": 0, "tracks": [[{"sound": s, "in": 0, "out": 1000, "level": 0.5}], []]}
    assert seqshape.read_shape(on_track_1) is None
    files.sequence_new("Bed")
    files.sequence_save("Bed", two([], [bed]), 0, 200)
    assert json.loads(seq_path(files, "Bed").read_text())["tracks"][1] == [bed], "written as given"
    assert files.sequence("Bed")["tracks"][1][0]["duck"] is True
