"""Save through the hub: an MP4 when track 1 holds clips, a WAV when it holds sounds or nothing; track 2's
sounds as the request's `audio`, cut at the file's end, one past it left out, a silent clip adding nothing; and a
recording from the computer (a WAV made by the browser) kept in Sounds by `POST /api/sounds/upload`."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from hub.modules.sequence import last
from tests.core.harness import Hub
from tests.engine.sequence_kit import clip, sound, two, whole
from tests.engine.test_sequence_module import open_hub
from tests.fakes.wav import tiny_wav


@pytest.fixture
async def hub(tmp_path: Path):  # type: ignore[no-untyped-def]
    h = await open_hub(tmp_path)
    last._last.clear()
    yield h
    await h.close()


PLAIN = {"level": 1.0, "fade_in": 0, "fade_out": 0, "duck": False}   # a track-2 item with nothing set


def real(hub: Hub, item: str) -> str:
    return os.path.realpath(hub.core.files.resolve(item))


async def save(hub: Hub, cookie: str) -> tuple[dict, dict]:
    joined = await hub.http("POST", "/api/sequence/join", cookie, json_body={"name": "Film"})
    assert joined.status == 200, joined.json()
    plan = hub.core.book.get(joined.json()["job"]).plan
    [task] = plan.tasks
    return task, plan.summary


async def test_clips_and_a_placed_sound_save_as_an_mp4_with_the_sound_cut_at_the_end(hub: Hub) -> None:
    files, cookie = hub.core.files, hub.pair()
    a, mute = clip(files, "101500-123"), clip(files, "101600-456", frames=48, fps=16)
    fx, late = sound(files, "120000-001", seconds=4.0), sound(files, "120000-002", seconds=1.0)
    files.sequence_new("Film")
    files.sequence_save("Film", two([{"clip": a, "in": 0, "out": 72}], [   # track 1: 3 s
        {"sound": fx, "in": 500, "out": 4000, "at": 1000},                  # 3.5 s from 1 s: cut to 2 s
        {**whole(mute, 48), "at": 0},                                       # no sound: adds nothing
        {"sound": late, "in": 0, "out": 1000, "at": 3000}]), 0, 200)       # starts at the end: left out
    task, summary = await save(hub, cookie)
    assert task["out_kind"] == "mp4" and task["canvas"] == {"w": 960, "h": 544, "fps": 24.0}
    assert task["audio"] == [{"path": real(hub, fx), "at_ms": 1000, "in": 500, "out": 2500, "fps": 1000.0, **PLAIN}]
    assert task["duck"] == {"threshold": 0.05, "ratio": 6.0, "attack": 50.0, "release": 400.0}, "the settings'"
    assert (summary["kind"], summary["seconds"], summary["clips"]) == ("clip", 3.0, 2)


async def test_a_beds_level_fades_and_duck_travel_with_the_save(tmp_path: Path) -> None:
    """The item's keys are kept by the file and carried on the join request; the settings' duck numbers."""
    hub = await open_hub(tmp_path, settings={"modules": {"sequence": {"duck_ratio": 4.0}}})
    files, cookie = hub.core.files, hub.pair()
    a, bed = clip(files, "101500-123"), sound(files, "120000-001", seconds=4.0)
    files.sequence_new("Film")
    saved = files.sequence_save("Film", two([{"clip": a, "in": 0, "out": 72}], [
        {"sound": bed, "in": 0, "out": 4000, "at": 0, "level": 0.5, "fade_in": 1000, "fade_out": 500, "duck": True},
        {"sound": bed, "in": 0, "out": 1000, "at": 1000, "level": 1.0, "fade_in": 0, "duck": False}]), 0, 200)
    assert saved["tracks"][1] == [
        {"sound": bed, "in": 0, "out": 4000, "at": 0, "level": 0.5, "fade_in": 1000, "fade_out": 500, "duck": True},
        {"sound": bed, "in": 0, "out": 1000, "at": 1000}], "defaults are not written"
    try:
        task, _ = await save(hub, cookie)
    finally:
        await hub.close()
    assert task["audio"][0] == {"path": real(hub, bed), "at_ms": 0, "in": 0, "out": 3000, "fps": 1000.0,
                                "level": 0.5, "fade_in": 1000, "fade_out": 500, "duck": True}
    assert task["audio"][1]["duck"] is False and task["duck"]["ratio"] == 4.0


async def test_sounds_on_track_1_save_as_a_wav(hub: Hub) -> None:
    files, cookie = hub.core.files, hub.pair()
    long = sound(files, "120000-001", seconds=40.0)
    files.sequence_new("Film")
    files.sequence_save("Film", two([{"sound": long, "in": 4000, "out": 19000}]), 0, 200)
    task, summary = await save(hub, cookie)
    assert task["out_kind"] == "wav" and task["canvas"] == {"w": 0, "h": 0, "fps": 1000.0}
    assert task["items"] == [{"path": real(hub, long), "in": 4000, "out": 19000, "fps": 1000.0, "w": 0, "h": 0,
                              "frames": 40000, "audio": True, "sound": True}]
    assert (summary["kind"], summary["seconds"], summary["title"]) == ("sound", 15.0, "Save · Film · 1 item")


async def test_track_2_alone_saves_as_a_wav_as_long_as_its_last_item(hub: Hub) -> None:
    files, cookie = hub.core.files, hub.pair()
    fx = sound(files, "120000-001", seconds=2.0)
    files.sequence_new("Film")
    files.sequence_save("Film", two([], [{"sound": fx, "in": 0, "out": 1500, "at": 3000}]), 0, 200)
    task, summary = await save(hub, cookie)
    assert (task["out_kind"], task["items"], summary["seconds"]) == ("wav", [], 4.5)
    assert task["audio"] == [{"path": real(hub, fx), "at_ms": 3000, "in": 0, "out": 1500, "fps": 1000.0, **PLAIN}]


async def test_a_recording_from_the_users_computer_lands_in_sounds(hub: Hub) -> None:
    files, cookie = hub.core.files, hub.pair()
    w = await hub.screen(cookie, "workspace", "w")
    up = await hub.http("POST", "/api/sounds/upload", cookie, body=tiny_wav(seconds=2.5, rate=48_000, tagged=True),
                        headers={"Content-Type": "audio/wav"})
    assert up.status == 200, up.json()
    made = up.json()
    assert made["seconds"] == 2.5 and files.kind(made["id"]) == "sound"
    assert b"LIST" not in files.resolve(made["id"]).read_bytes(), "only its sound is kept"
    assert (await w.recv("media.changed", timeout=2))["d"] == {"what": "sounds"}
    assert not [p for p in files.roots["out"].rglob(".up-*")], "no temp file left"
    bad = await hub.http("POST", "/api/sounds/upload", cookie, body=b"not a sound",
                         headers={"Content-Type": "audio/wav"})
    assert (bad.status, bad.json()["text"]) == (400, "That sound file could not be read")
    mp3 = await hub.http("POST", "/api/sounds/upload", cookie, body=b"ID3", headers={"Content-Type": "audio/mpeg"})
    assert mp3.status == 415, "the browser converts it first"
