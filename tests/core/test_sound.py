"""Sounds: the fifth media root (`<data>/sounds`, ids `sounds/<day>/<time>.wav`), a WAV kept as its
sound and nothing else (`hub/core/sound.py`), and how an engine's WAV lands there."""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

from hub.core import api, enginecat, sound
from hub.core.engine import EngineLane
from hub.core.files import Files
from hub.core.supervisor import EngineFailed, Spawn, worker_env
from tests.fakes.wav import SECRET, chunk_ids, float32, tiny_wav

FAKE_WORKER = Path(__file__).resolve().parent.parent / "fakes" / "fake_worker.py"


def test_strip_keeps_the_format_and_the_sound_only(tmp_path: Path) -> None:
    path = tmp_path / "a.wav"
    path.write_bytes(tiny_wav(0.5, tagged=True))
    assert chunk_ids(path.read_bytes()) == [b"fmt ", b"LIST", b"JUNK", b"data"]
    sound.strip(path)
    raw = path.read_bytes()
    assert chunk_ids(raw) == [b"fmt ", b"data"] and SECRET not in raw
    assert raw == tiny_wav(0.5), "the sound itself, byte for byte"
    assert struct.unpack("<I", raw[4:8])[0] == len(raw) - 8, "the RIFF size is the file's"
    assert sound.facts(path) == {"seconds": 0.5}
    assert [p.name for p in tmp_path.iterdir()] == ["a.wav"], "no temporary file left"


def test_a_float_wav_keeps_its_fact_chunk(tmp_path: Path) -> None:
    path = tmp_path / "f.wav"
    path.write_bytes(float32(2.0))
    sound.strip(path)
    assert chunk_ids(path.read_bytes()) == [b"fmt ", b"fact", b"data"]
    assert sound.facts(path) == {"seconds": 2.0}


@pytest.mark.parametrize("raw", [b"RIFF....WAVE", b"not a sound at all", b"RIFF\x04\x00\x00\x00AVI "])
def test_what_is_not_a_wav_is_refused_and_left_alone(tmp_path: Path, raw: bytes) -> None:
    path = tmp_path / "x.wav"
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        sound.strip(path)
    assert path.read_bytes() == raw


def test_a_format_the_hub_does_not_read_is_refused(tmp_path: Path) -> None:
    raw = bytearray(tiny_wav(0.1))
    raw[20:22] = struct.pack("<H", 0x55)                     # MPEG layer 3 in a WAV
    (tmp_path / "x.wav").write_bytes(bytes(raw))
    with pytest.raises(ValueError, match="does not read"):
        sound.strip(tmp_path / "x.wav")


def test_the_sounds_root_and_its_kind(tmp_path: Path) -> None:
    files = Files(tmp_path / "data")
    assert files.roots["sounds"] == tmp_path / "data" / "sounds" and files.roots["sounds"].is_dir()
    (files.roots["sounds"] / "2026-10-17").mkdir()
    (files.roots["sounds"] / "2026-10-17" / "120000-000.wav").write_bytes(tiny_wav(1.5))
    item = "sounds/2026-10-17/120000-000.wav"
    assert files.kind(item) == "sound" and files.kind("out/2026-10-17/a.wav") is None and files.kind(
        "sounds/2026-10-17/a.png") is None
    assert files.sound_facts(item) == {"seconds": 1.5} and files.thumb_url(item) is None
    assert files.existing_media(item).is_file()
    with pytest.raises(api.Invalid, match="no thumbnail"):
        files.thumbnail(item, 336)
    with pytest.raises(api.Invalid, match="Sounds stay in Sounds"):
        files.move([item], "")
    assert files.delete([item]) == [item] and not files.resolve(item).exists()


def outbox_with(tmp_path: Path, name: str, data: bytes) -> tuple[Path, Path]:
    outbox, outputs = tmp_path / "outbox", tmp_path / "outputs"
    outbox.mkdir()
    outputs.mkdir()
    (outbox / name).write_bytes(data)
    return outbox, outputs


def test_a_wav_lands_in_sounds_stripped_its_name_the_time(tmp_path: Path) -> None:
    outbox, outputs = outbox_with(tmp_path, "2026-10-17-12h00m00s_seed7_Speaker 1 hello.wav", tiny_wav(1, tagged=True))
    landed = enginecat.land(str(next(outbox.iterdir())), outbox, outputs, tmp_path / "clips", tmp_path / "sounds")
    assert landed["kind"] == "sound" and landed["seconds"] == 1.0 and landed["id"].startswith("sounds/")
    dest = tmp_path / "sounds" / landed["id"][7:]
    assert dest.read_bytes() == tiny_wav(1) and "hello" not in dest.name and "seed" not in dest.name
    assert not list(outbox.iterdir()) and not list(outputs.iterdir())


def test_a_wav_that_does_not_read_fails_the_job_in_one_line(tmp_path: Path) -> None:
    outbox, outputs = outbox_with(tmp_path, "x.wav", b"RIFF....WAVE")
    with pytest.raises(EngineFailed) as err:
        enginecat.land(str(outbox / "x.wav"), outbox, outputs, tmp_path / "clips", tmp_path / "sounds")
    assert err.value.text == "The engine wrote a sound the hub could not read"
    assert not list(outbox.iterdir()) and not (tmp_path / "sounds").exists()


async def test_the_lane_lands_a_sound_and_says_so(tmp_path: Path) -> None:
    spawn = Spawn(sys.executable, ("--root", str(tmp_path), "--state", str(tmp_path / "s"), "--", "wav"),
                  worker_env(tmp_path / "h", "0"), tmp_path / "w.pid", FAKE_WORKER)
    eng = EngineLane("image.gpu0", None, spawn, tmp_path / "data", tmp_path / "s", "key")
    task = api.request_wire(api.SpeechRequest("fake_model", "Hello.", 1, 300))
    job = api.Job(id="j_1", kind="generate-image.image", tool="generate-image", state="running",
                  plan=api.JobPlan("image", "fake_model", (task,), {}))
    events: list[tuple[str, dict]] = []
    try:
        await eng.run(job, lambda e, d: events.append((e, d)))
    finally:
        await eng.stop()
    [out] = [d for e, d in events if e == "output"]
    assert out["kind"] == "sound" and out["item"].startswith("sounds/") and out["seconds"] == 1.0
    assert (tmp_path / "data" / "sounds" / out["item"][7:]).read_bytes() == tiny_wav(1)
