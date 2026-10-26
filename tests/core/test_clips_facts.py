"""What a clip is, read from its boxes (`clip.facts`): size, frame rate, frames, seconds, sound; carried by the
landing and by the generation the media screen hears."""
from __future__ import annotations

import struct
from pathlib import Path

import pytest

from hub.core import clip, enginecat
from hub.core.api import JobPlan, Module, Tab
from hub.core.supervisor import EngineFailed
from tests.core.fake_lane import FakeLane
from tests.core.harness import Hub, own_modules, start_hub
from tests.core.test_clips import BAD, outbox_with, tagged
from tests.fakes.fake_probes import FakeProbes
from tests.fakes.mp4 import FTYP, MVHD_BODY, SCALE, box, tagged_mp4, tiny_mp4


# ---------------------------------------------------------------- facts
@pytest.mark.parametrize("audio", [False, True], ids=["silent", "with sound"])
def test_facts_are_read_from_the_boxes(tmp_path: Path, audio: bool) -> None:
    path = tagged(tmp_path, tiny_mp4(audio=audio))
    assert clip.facts(path) == {"w": 960, "h": 544, "fps": 24.0, "frames": 124, "seconds": 5.167, "audio": audio}
    assert path.read_bytes() == tiny_mp4(audio=audio), "reading changes nothing"


def test_facts_follow_the_file_not_the_defaults(tmp_path: Path) -> None:
    path = tagged(tmp_path, tiny_mp4(w=1280, h=704, fps=16, frames=81))
    assert clip.facts(path) == {"w": 1280, "h": 704, "fps": 16.0, "frames": 81, "seconds": 5.062, "audio": False}


@pytest.mark.parametrize("large", [False, True], ids=["version 0", "version 1"])
def test_facts_of_a_tagged_clip_survive_the_cut(tmp_path: Path, large: bool) -> None:
    path = tagged(tmp_path, tagged_mp4(large=large))
    want = {"w": 960, "h": 544, "fps": 24.0, "frames": 3, "seconds": 0.125, "audio": False}
    assert clip.facts(path) == want
    assert clip.strip(path) is True and clip.facts(path) == want


@pytest.mark.parametrize("audio", [False, True], ids=["silent", "with sound"])
def test_a_landed_clip_reports_its_size_and_length(tmp_path: Path, audio: bool) -> None:
    outbox, outputs = outbox_with(tmp_path, "x.mp4", tiny_mp4(audio=audio))
    landed = enginecat.land(str(outbox / "x.mp4"), outbox, outputs, tmp_path / "clips")
    assert {k: landed[k] for k in ("kind", "w", "h", "seconds")} == {"kind": "clip", "w": 960, "h": 544,
                                                                      "seconds": 5.167}


def _swap(data: bytes, old: bytes, new: bytes) -> bytes:
    assert data.count(old) == 1
    return data.replace(old, new)


UNREADABLE = {
    **BAD,
    "no track": box(b"ftyp", FTYP) + box(b"moov", box(b"mvhd", MVHD_BODY)) + box(b"mdat", b"x" * 40),
    "sound only": _swap(tiny_mp4(), b"vide", b"soun"),
    "tables disagree": _swap(tiny_mp4(), b"stsz" + struct.pack(">III", 0, 1, 124),
                             b"stsz" + struct.pack(">III", 0, 1, 125)),
    "no timescale": _swap(tiny_mp4(), b"mdhd" + bytes(12) + struct.pack(">I", SCALE), b"mdhd" + bytes(16)),
    "torn time table": _swap(tiny_mp4(), b"stts" + struct.pack(">II", 0, 2), b"stts" + struct.pack(">II", 0, 99)),
    "short track header": _swap(tiny_mp4(), struct.pack(">I4s", 92, b"tkhd"), struct.pack(">I4s", 12, b"tkhd")),
}


@pytest.mark.parametrize("name", list(UNREADABLE))
def test_a_clip_without_readable_facts_is_refused(tmp_path: Path, name: str) -> None:
    data = UNREADABLE[name]
    with pytest.raises(ValueError):
        clip.facts(tagged(tmp_path, data))
    assert (tmp_path / "x.mp4").read_bytes() == data
    outbox, outputs = outbox_with(tmp_path, "y.mp4", data)
    with pytest.raises(EngineFailed) as err:
        enginecat.land(str(outbox / "y.mp4"), outbox, outputs, tmp_path / "clips")
    assert err.value.text == "The engine wrote a clip the hub could not read"
    assert not list(outbox.iterdir()) and not (tmp_path / "clips").exists()



# ---------------------------------------------------------------- the generation item
class ClipLane(FakeLane):
    """The fake lane, its clip landed as the engine lane lands one: size and seconds read from the file."""

    def _clip(self, job_id: str, k: int, emit) -> None:  # type: ignore[no-untyped-def]
        folder = self.outputs.parent / "clips" / "2026-10-09"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{job_id}_{k}.mp4"
        path.write_bytes(tiny_mp4(audio=True))
        seen = clip.facts(path)
        emit("output", {"task": k, "item": f"clips/2026-10-09/{path.name}", "kind": "clip", "w": seen["w"],
                        "h": seen["h"], "seconds": seen["seconds"]})
        emit("task_done", {"task": k, "seconds": 0.1, "peak_vram_mb": 14_000, "peak_rss_mb": 9_000})


def build(params: dict, ctx) -> JobPlan:  # type: ignore[no-untyped-def]
    return JobPlan(lane_kind="image", model="fake", tasks=({"seed": 1},), summary={"model": "Fake"})


async def test_the_generation_item_carries_size_and_seconds(tmp_path: Path) -> None:
    probes = FakeProbes()
    lane = ClipLane(tmp_path / "data" / "outputs", probes)
    lane.video = True
    gen = Module(id="gen", title="Gen", tab=Tab("Gen", 10), jobs={"image": build})
    hub: Hub = await start_hub(tmp_path / "data", lanes=[lane], modules=[*own_modules(), gen], probes=probes)
    try:
        cookie = hub.pair()
        w, m = await hub.screen(cookie, "workspace", "w"), await hub.screen(cookie, "media", "m")
        await w.send("job.submit", {"tool": "gen", "kind": "image", "params": {}}, id="r1")
        job_id = (await w.recv(where=lambda x: x.get("re") == "r1"))["d"]["job"]
        item = (await m.recv("generation", timeout=5))["d"]["item"]
    finally:
        await hub.close()
    assert item["id"] == f"clips/2026-10-09/{job_id}_1.mp4" and item["kind"] == "clip"
    assert item["thumb"].startswith("/thumbs/clips/")                  # 1be310f: a clip's thumbnail is its first frame
    assert (item["w"], item["h"], item["seconds"]) == (960, 544, 5.167)
