"""Clips: the fourth media root (`<data>/clips`, ids `clips/<day>/<time>.mp4`) and how an engine's MP4 lands there."""
from __future__ import annotations

import io
import struct
import sys
from pathlib import Path

import pytest
from PIL import Image

from hub.core import api, clip, enginecat
from hub.core.api import Invalid
from hub.core.engine import EngineLane
from hub.core.files import Files, temp_path
from hub.core.supervisor import EngineFailed, Spawn, worker_env
from tests.fakes.mp4 import CHUNKS, TAGS, box, chunk_offsets, chunks, read, tagged_mp4, tiny_mp4

FAKE_WORKER = Path(__file__).resolve().parent.parent / "fakes" / "fake_worker.py"


def png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 6), (1, 2, 3)).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def files(tmp_path: Path) -> Files:
    f = Files(tmp_path / "data")
    (f.roots["clips"] / "2026-10-09").mkdir()
    (f.roots["clips"] / "2026-10-09" / "120000-000.mp4").write_bytes(tiny_mp4())
    (f.roots["clips"] / "2026-10-09" / "stray.png").write_bytes(png_bytes())
    (f.roots["out"] / "2026-10-09").mkdir()
    (f.roots["out"] / "2026-10-09" / "a.png").write_bytes(png_bytes())
    (f.roots["out"] / "2026-10-09" / "b.mp4").write_bytes(tiny_mp4())
    return f


def test_the_clips_root_is_made_beside_temp(files: Files) -> None:
    assert files.roots["clips"] == files.data_dir / "clips" and files.roots["clips"].is_dir()
    own = ["clips", "outputs", "scripts", "sets", "sounds"]                          # 002, 041, 094
    assert sorted(p.name for p in files.data_dir.iterdir()) == own


def test_kinds_and_existing_media(files: Files) -> None:
    clip = "clips/2026-10-09/120000-000.mp4"
    assert files.kind(clip) == "clip" and files.kind("out/2026-10-09/a.png") == "image"
    assert files.kind("clips/2026-10-09/stray.png") is None, "the clips root holds clips only"
    assert files.kind("out/2026-10-09/b.mp4") is None, "Temp holds pictures only"
    assert files.existing_media(clip).read_bytes() == tiny_mp4()
    assert files.existing_media("out/2026-10-09/a.png").is_file()
    for item in ("clips/2026-10-09/stray.png", "out/2026-10-09/b.mp4", "clips/2026-10-09/gone.mp4", "clips/../x"):
        with pytest.raises(Invalid):
            files.existing_media(item)
    with pytest.raises(Invalid):
        files.existing_image(clip)
    assert files.item_for(files.roots["clips"] / "2026-10-09" / "120000-000.mp4") == clip


def test_urls_and_no_thumbnail_for_a_clip(files: Files) -> None:
    clip = "clips/2026-10-09/120000-000.mp4"
    assert files.url(clip).startswith("/files/clips/2026-10-09/120000-000.mp4?v=")
    assert files.thumb_url(clip).startswith("/thumbs/clips/")          # 1be310f: a clip's thumbnail is its first frame
    assert files.thumb_url("out/2026-10-09/a.png").startswith("/thumbs/out/2026-10-09/a.png/336?v=")
    with pytest.raises(Invalid) as err:
        files.thumbnail(clip, 336)
    assert err.value.text == "This clip gives no frame", "1be310f: its first frame; this stand-in has none"


def test_delete_takes_clips_regroup_leaves_them_and_the_drive_refuses_them(files: Files, tmp_path: Path) -> None:
    clip = "clips/2026-10-09/120000-000.mp4"
    assert files.regroup([clip], "Best") == [] and files.existing_media(clip).is_file(), "clips stay flat"
    files.set_drive(tmp_path / "Drive")
    (tmp_path / "Drive").mkdir()
    with pytest.raises(Invalid) as err:
        files.move([clip], "")
    assert err.value.text == "Clips stay in the clips folder for now"
    assert files.existing_media(clip).is_file(), "nothing moved"
    assert files.delete([clip, "clips/2026-10-09/stray.png"]) == [clip]
    assert not (files.roots["clips"] / "2026-10-09" / "120000-000.mp4").exists()


def test_a_clip_is_named_by_the_time_like_a_picture(tmp_path: Path) -> None:
    path = temp_path(tmp_path / "clips", ".MP4")
    assert path.suffix == ".mp4" and len(path.name) == len("HHMMSS-mmm.mp4")
    assert path.parent.parent == tmp_path / "clips"


# ---------------------------------------------------------------- landing
def outbox_with(tmp_path: Path, name: str, data: bytes) -> tuple[Path, Path]:
    outbox, outputs = tmp_path / "outbox", tmp_path / "outputs"
    outbox.mkdir()
    outputs.mkdir()
    (outbox / name).write_bytes(data)
    return outbox, outputs


def test_an_untagged_mp4_lands_in_the_clips_root_untouched_without_pillow(tmp_path: Path, monkeypatch) -> None:
    def no_pillow(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("Pillow never opens a clip")
    monkeypatch.setattr(enginecat.clean, "strip", no_pillow)
    monkeypatch.setattr(enginecat.Image, "open", no_pillow)
    outbox, outputs = outbox_with(tmp_path, "2026-10-12-1234.mp4", tiny_mp4())
    landed = enginecat.land(str(outbox / "2026-10-12-1234.mp4"), outbox, outputs, tmp_path / "clips")
    assert landed["kind"] == "clip" and (landed["w"], landed["h"], landed["seconds"]) == (960, 544, 5.167)
    assert landed["id"].startswith("clips/") and landed["id"].endswith(".mp4") and "1234" not in landed["id"]
    assert (tmp_path / "clips" / landed["id"][6:]).read_bytes() == tiny_mp4()
    assert not list(outbox.iterdir()) and not list(outputs.iterdir()), "nothing in Temp"


def test_a_picture_still_lands_in_temp_as_a_dict(tmp_path: Path) -> None:
    outbox, outputs = outbox_with(tmp_path, "x.png", png_bytes())
    landed = enginecat.land(str(outbox / "x.png"), outbox, outputs, tmp_path / "clips")
    assert landed["kind"] == "image" and (landed["w"], landed["h"]) == (8, 6) and landed["id"].startswith("out/")
    assert not (tmp_path / "clips").exists()


@pytest.mark.parametrize("name", ["x.mkv", "x"])          # a WAV lands in Sounds (tests/core/test_sound.py)
def test_any_other_file_fails_the_job_loudly(tmp_path: Path, name: str) -> None:
    outbox, outputs = outbox_with(tmp_path, name, b"RIFF....WAVE")
    with pytest.raises(EngineFailed) as err:
        enginecat.land(str(outbox / name), outbox, outputs, tmp_path / "clips")
    assert err.value.text == "The engine wrote a file the hub does not take"
    assert not list(outbox.iterdir()) and not list(outputs.iterdir())


def lane(tmp_path: Path, mode: str) -> EngineLane:
    spawn = Spawn(sys.executable, ("--root", str(tmp_path), "--state", str(tmp_path / "s"), "--", mode),
                  worker_env(tmp_path / "h", "0"), tmp_path / "w.pid", FAKE_WORKER)
    return EngineLane("image.gpu0", None, spawn, tmp_path / "data", tmp_path / "s", "key")


def job() -> api.Job:
    task = api.request_wire(api.ClipRequest("fake_model", "a shot", (960, 544), 1, 124, steps=2))   # as a module sends
    return api.Job(id="j_1", kind="generate-image.image", tool="generate-image", state="running",
                   plan=api.JobPlan("image", "fake_model", (task,), {}))


async def test_the_lane_lands_a_clip_and_says_so(tmp_path: Path) -> None:
    events: list[tuple[str, dict]] = []
    eng = lane(tmp_path, "video")
    try:
        await eng.run(job(), lambda e, d: events.append((e, d)))
    finally:
        await eng.stop()
    [out] = [d for e, d in events if e == "output"]
    assert out["kind"] == "clip" and out["item"].startswith("clips/") and (out["w"], out["h"]) == (960, 544)
    assert out["seconds"] == 5.167
    assert (tmp_path / "data" / "clips" / out["item"][6:]).read_bytes() == tiny_mp4()



# ---------------------------------------------------------------- tags cut
def kinds(data: bytes) -> list[tuple[bytes, ...]]:
    return [path for path, *_ in read(data)]


def assert_clean(data: bytes) -> None:
    paths = kinds(data)
    assert not [p for p in paths if b"udta" in p or p[:2] == (b"moov", b"meta") or set(p) & set(TAGS)]
    assert (b"moov", b"trak", b"mdia", b"minf", b"stbl") in paths and (b"moov", b"mvhd") in paths
    assert chunks(data) == list(CHUNKS), "every chunk offset still points at its frame"


def tagged(tmp_path: Path, data: bytes) -> Path:
    path = tmp_path / "x.mp4"
    path.write_bytes(data)
    return path


@pytest.mark.parametrize("large", [False, True], ids=["32-bit", "64-bit"])
def test_tags_are_cut_and_offsets_follow_the_data_when_moov_comes_first(tmp_path: Path, large: bool) -> None:
    before = tagged_mp4(moov_first=True, large=large)
    assert {p[-1] for p in kinds(before)} >= {b"udta", b"meta", *TAGS} and chunks(before) == list(CHUNKS)
    path = tagged(tmp_path, before)
    assert clip.strip(path) is True
    after = path.read_bytes()
    assert_clean(after)
    assert [p for p in kinds(after) if len(p) == 1] == [(b"ftyp",), (b"moov",), (b"mdat",)], "order kept"
    delta = len(before) - len(after)
    assert delta > 0 and chunk_offsets(after) == [o - delta for o in chunk_offsets(before)]
    table = b"co64" if large else b"stco"
    assert any(p[-1] == table for p in kinds(after))
    [(_, _, moov_head, moov_size)] = [b for b in read(after) if b[0] == (b"moov",)]
    [(_, _, mdat_head, mdat_size)] = [b for b in read(after) if b[0] == (b"mdat",)]
    assert (moov_head, mdat_head) == ((16, 16) if large else (8, 8)), "64-bit headers keep their form"
    assert after[-mdat_size:] == before[-mdat_size:], "the media data is copied as it was"
    assert clip.strip(path) is False and path.read_bytes() == after, "a clean clip is left alone"


def test_offsets_stay_when_moov_comes_after_the_data(tmp_path: Path) -> None:
    before = tagged_mp4(moov_first=False)
    path = tagged(tmp_path, before)
    assert clip.strip(path) is True
    after = path.read_bytes()
    assert_clean(after)
    assert [p for p in kinds(after) if len(p) == 1] == [(b"ftyp",), (b"mdat",), (b"moov",)]
    assert chunk_offsets(after) == chunk_offsets(before) and len(after) < len(before)


def test_a_fragmented_clip_keeps_every_byte_in_place(tmp_path: Path) -> None:
    before = tagged_mp4() + box(b"moof", box(b"mfhd", bytes(8)))
    path = tagged(tmp_path, before)
    assert clip.strip(path) is True
    after = path.read_bytes()
    assert len(after) == len(before) and chunk_offsets(after) == chunk_offsets(before)
    assert_clean(after)
    assert b"Encoder" not in after and b"a prompt" not in after and any(p[-1] == b"free" for p in kinds(after))


def test_an_untagged_clip_is_not_rewritten(tmp_path: Path) -> None:
    path = tagged(tmp_path, tiny_mp4())
    stamp = path.stat().st_mtime_ns
    assert clip.strip(path) is False and path.read_bytes() == tiny_mp4() and path.stat().st_mtime_ns == stamp


BAD = {
    "empty": b"",
    "text": b"not an mp4 at all, just words",
    "picture": png_bytes(),
    "torn": tagged_mp4()[:-5],
    "no ftyp": tagged_mp4()[32:],
    "no moov": box(b"ftyp", b"isom") + box(b"mdat", b"x" * 40),
    "two moovs": box(b"ftyp", b"isom") + box(b"moov", b"") + box(b"moov", b""),
    "wild offset": tagged_mp4().replace(struct.pack(">I", chunk_offsets(tagged_mp4())[0]), b"\xff" * 4, 1),
}


@pytest.mark.parametrize("name", list(BAD))
def test_a_file_that_is_not_an_mp4_is_refused(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError):
        clip.strip(tagged(tmp_path, BAD[name]))
    assert (tmp_path / "x.mp4").read_bytes() == BAD[name] and [p.name for p in tmp_path.iterdir()] == ["x.mp4"]
    outbox, outputs = outbox_with(tmp_path, "y.mp4", BAD[name])
    with pytest.raises(EngineFailed) as err:
        enginecat.land(str(outbox / "y.mp4"), outbox, outputs, tmp_path / "clips")
    assert err.value.text == "The engine wrote a clip the hub could not read"
    assert not list(outbox.iterdir()) and not (tmp_path / "clips").exists()


def test_a_tagged_clip_lands_without_its_tags(tmp_path: Path) -> None:
    outbox, outputs = outbox_with(tmp_path, "x.mp4", tagged_mp4())
    landed = enginecat.land(str(outbox / "x.mp4"), outbox, outputs, tmp_path / "clips")
    assert landed["kind"] == "clip" and (landed["w"], landed["h"], landed["seconds"]) == (960, 544, 0.125)
    assert_clean((tmp_path / "clips" / landed["id"][6:]).read_bytes())
    assert not list(outbox.iterdir())

